"""
Runs an evaluation based upon a given evaluation specification
"""
import os
import typing
import json
import logging

import polars

from dmod.metrics.communication import Verbosity
import dmod.metrics as metrics

import dmod.core.common as common

from . import specification
from . import crosswalk
from . import data_retriever
from . import threshold
from . import measurement_units

COMMUNICATORS = typing.Union[metrics.Communicator, typing.Sequence[metrics.Communicator]]


class UnitConverter:
    """
    A callable that converts the value from one column in a pandas Series from its meaurement unit to
    that of another measurement unit
    """
    def __init__(self, value_field: str, from_unit_field: str, to_unit_field: str):
        self.__value_field = value_field
        self.__from_unit_field = from_unit_field
        self.__to_unit_field = to_unit_field

    def __call__(self, frame: polars.DataFrame) -> polars.DataFrame:
        return measurement_units.convert_frame(
            frame=frame,
            value_column=self.__value_field,
            from_unit=self.__from_unit_field,
            to_unit=self.__to_unit_field
        )


class Evaluator:
    def __init__(
        self,
        instructions: typing.Union[specification.EvaluationSpecification, str, dict],
        communicators: COMMUNICATORS = None,
        verbosity: Verbosity = None
    ):
        if isinstance(instructions, str):
            instructions = json.loads(instructions)

        if isinstance(instructions, dict):
            instructions = specification.EvaluationSpecification.create(instructions)

        self._instructions = instructions

        self._observed_location_field: typing.Optional[str] = None
        self._predicted_location_field: typing.Optional[str] = None
        self._observed_value_field: typing.Optional[str] = None
        self._predicted_value_field: typing.Optional[str] = None
        self._observed_xaxis: typing.Optional[str] = None
        self._predicted_xaxis: typing.Optional[str] = None
        self._verbosity = verbosity or Verbosity.QUIET

        if isinstance(communicators, metrics.CommunicatorGroup):
            self._communicators: metrics.CommunicatorGroup = communicators
        elif isinstance(communicators, (typing.Iterable, metrics.Communicator)):
            self._communicators: metrics.CommunicatorGroup = metrics.CommunicatorGroup(communicators)
        else:
            self._communicators: metrics.CommunicatorGroup = metrics.CommunicatorGroup()

        self._set_field_names()
        self._converter = UnitConverter(self._predicted_value_field, "unit_prediction", "unit_observation")

    @property
    def instructions(self) -> specification.EvaluationSpecification:
        """
        The specification telling the Evaluator what to do
        """
        return self._instructions

    @property
    def maximum_score(self) -> float:
        """
        Returns:
            The maximum possible score of a whole evaluation
        """
        total_threshold_weights = sum(self._instructions.thresholds)
        total_metric_weights = sum(metric.weight for metric in self._instructions.scheme.metric_functions)

        weight_per_location = total_metric_weights + total_threshold_weights
        return weight_per_location

    def _set_field_names(self):
        error_messages = []

        observed_xaxis = None
        observed_value_field = None

        for observation_definition in self._instructions.observations:
            xaxis = observation_definition.x_axis
            value_field = observation_definition.value_field

            observed_xaxis_is_mismatched = observed_xaxis is not None and observed_xaxis != xaxis
            observed_value_field_is_mismatched = observed_value_field is not None
            observed_value_field_is_mismatched &= observed_value_field != value_field

            if observed_xaxis_is_mismatched:
                error_messages.append("Cannot collect observation data - the xaxis definition is not uniform")

            if observed_value_field_is_mismatched:
                error_messages.append("Cannot collect observation data - value label definitions are not uniform")

            if observed_xaxis_is_mismatched or observed_value_field_is_mismatched:
                break

            observed_xaxis = xaxis
            observed_value_field = value_field

        self._observed_xaxis = observed_xaxis
        self._observed_value_field = observed_value_field

        predicted_xaxis = None
        predicted_value_field = None

        for prediction_definition in self._instructions.predictions:
            xaxis = prediction_definition.x_axis
            value_field = prediction_definition.value_field

            predicted_xaxis_is_mismatched = predicted_xaxis is not None and predicted_xaxis != xaxis
            predicted_value_field_is_mismatched = predicted_value_field is not None
            predicted_value_field_is_mismatched &= predicted_value_field != value_field

            if predicted_xaxis_is_mismatched:
                error_messages.append("Cannot collect prediction data - the xaxis definition is not uniform")

            if predicted_value_field_is_mismatched:
                error_messages.append("Cannot collect prediction data - value label definitions are not uniform")

            if predicted_xaxis_is_mismatched or predicted_value_field_is_mismatched:
                break

            predicted_xaxis = xaxis
            predicted_value_field = value_field

        self._predicted_xaxis = predicted_xaxis or observed_xaxis
        self._predicted_value_field = predicted_value_field or observed_value_field

        observed_location_label = None
        predicted_location_label = None

        for crosswalk_definition in self._instructions.crosswalks:
            observed_is_mismatched = observed_location_label is not None
            observed_is_mismatched &= crosswalk_definition.observation_field_name != observed_location_label

            predicted_is_mismatched = predicted_location_label is not None
            predicted_is_mismatched &= crosswalk_definition.prediction_field_name != predicted_location_label

            if observed_is_mismatched and predicted_is_mismatched:
                message = f"Crosswalk cannot be compiled - new field names for observed locations and predicted " \
                          f"locations ({crosswalk_definition.observation_field_name} and " \
                          f"{crosswalk_definition.prediction_field_name}) don't match previous " \
                          f"field names ({observed_location_label} and {predicted_location_label})"
                mismatch_exception = ValueError(message)
                self._communicators.error(
                    message,
                    mismatch_exception,
                    verbosity=Verbosity.NORMAL,
                    publish=True
                )

                raise mismatch_exception

            if observed_is_mismatched:
                message = f"Crosswalk cannot be compiled - the new field name for observed locations " \
                          f"({crosswalk_definition.observation_field_name}) does not match the previous " \
                          f"field name ({observed_location_label})"
                mismatch_exception = ValueError(message)

                self._communicators.error(
                    message,
                    mismatch_exception,
                    verbosity=Verbosity.NORMAL,
                    publish=True
                )

                raise mismatch_exception

            if predicted_is_mismatched:
                message = f"Crosswalk cannot be compiled - the new field name for prediction locations " \
                          f"({crosswalk_definition.prediction_field_name}) does not match the previous " \
                          f"field name ({predicted_location_label})"
                mismatch_exception = ValueError(message)

                self._communicators.error(
                    message,
                    mismatch_exception,
                    verbosity=Verbosity.NORMAL,
                    publish=True
                )

                raise mismatch_exception

            observed_location_label = crosswalk_definition.observation_field_name
            predicted_location_label = crosswalk_definition.prediction_field_name

        self._observed_location_field = observed_location_label
        self._predicted_location_field = predicted_location_label or observed_location_label

    def evaluate(self) -> specification.EvaluationResults:
        """
        Uses stored Evaluator data to score predictions compared to observations

        Returns:
            Scoring results tied to crosswalk identifiers
        """
        crosswalk_data = self.get_crosswalk()

        if self._verbosity == Verbosity.ALL and self._communicators.send_all():
            self._communicators.write(reason="crosswalk", data=crosswalk_data.to_dict(), verbosity=Verbosity.ALL)

        data_to_evaluate = self.get_data_to_evaluate(crosswalk_data)
        data_to_evaluate = self.normalize_values(data_to_evaluate)

        self._communicators.info(
            "Data to evaluate has been collected",
            verbosity=Verbosity.LOUD,
            publish=True
        )

        thresholds = self.get_thresholds()

        self._communicators.info(
            "Thresholds have been collected",
            verbosity=Verbosity.LOUD,
            publish=True
        )

        # Score data and arrange in a dictionary like (observed location, forecasted location) => MetricResults
        scores: typing.Dict[typing.Tuple[str, str], metrics.MetricResults] = self.score(data_to_evaluate, thresholds)

        evaluation_results = specification.EvaluationResults(self._instructions, scores)

        if self._verbosity == Verbosity.ALL and self._communicators.send_all():
            data = evaluation_results.to_dict()
            self._communicators.write(reason="evaluation_result", data=data, verbosity=Verbosity.ALL)

        return evaluation_results

    def get_crosswalk(self) -> polars.DataFrame:
        """
        Gathers crosswalk data as specified via the instructions

        Returns:
            A DataFrame describing the mapping between observation and predicted locations
        """
        crosswalk_data: typing.Optional[polars.DataFrame] = None
        crosswalks: typing.List[polars.DataFrame] = []
        for crosswalk_definition in self._instructions.crosswalks:
            found_crosswalk = crosswalk.get_data(crosswalk_definition)

            if found_crosswalk is None or found_crosswalk.empty:
                continue
            crosswalks.append(found_crosswalk)

        if crosswalk_data is None or len(crosswalk_data) == 0:
            message = "No crosswalk data could be found"
            missing_data_exception = ValueError(message)

            additional_information = []

            common.on_each(
                lambda cross: additional_information.append(f"No crosswalk data was found at {str(cross)}"),
                self._instructions.crosswalks
            )

            missing_data_details = os.linesep + os.linesep.join(additional_information)

            self._communicators.error(
                message + missing_data_details,
                missing_data_exception,
                verbosity=Verbosity.NORMAL,
                publish=True
            )

            raise missing_data_exception

        crosswalk_data = polars.concat(crosswalks)

        return crosswalk_data

    def get_data_to_evaluate(self, crosswalk_data: polars.DataFrame) -> polars.DataFrame:
        """
        Uses internal specification and discovered crosswalk data to organize what data to evaluate and how

        Args:
            crosswalk_data:
                A DataFrame describing what locations bind together
        Returns:
            A DataFrame of observed and predicted data matched together for evaluation
        """
        observations: typing.Optional[polars.DataFrame] = None
        observation_frames: typing.List[polars.DataFrame] = []
        self._communicators.info(
            "Loading evaluation input data",
            verbosity=Verbosity.LOUD,
            publish=True
        )

        for observation_definition in self._instructions.observations:
            found_observations = data_retriever.read(observation_definition)

            if found_observations is None or len(found_observations) == 0:
                continue

            observation_frames.append(found_observations)

        if observation_frames:
            observations = polars.concat(observation_frames)
        else:
            message = "No observation data could be found"

            additional_information = []

            common.on_each(
                lambda observation_source: additional_information.append(f"No observation data was found at {str(observation_source)}"),
                self._instructions.observations
            )

            missing_data_details = message + os.linesep + os.linesep.join(additional_information)

            missing_data_exception = ValueError(missing_data_details)

            self._communicators.error(
                message + missing_data_details,
                missing_data_exception,
                verbosity=Verbosity.NORMAL,
                publish=True
            )

            raise missing_data_exception

        self._communicators.info(
            "Finished loading observation data",
            verbosity=Verbosity.LOUD,
            publish=True
        )

        predictions: typing.Optional[polars.DataFrame] = None
        prediction_frames: typing.List[polars.DataFrame] = []

        for prediction_definition in self._instructions.predictions:
            found_predictions = data_retriever.read(prediction_definition)

            if found_predictions is None or len(found_predictions) == 0:
                continue

            prediction_frames.append(found_predictions)

        if prediction_frames:
            predictions = polars.concat(prediction_frames)
        else:

            message = "No prediction data could be found"

            additional_information = []

            common.on_each(
                lambda prediction_source: additional_information.append(
                    f"No prediction data was found at {str(prediction_source)}"
                ),
                self._instructions.observations
            )

            missing_data_details = message + os.linesep + os.linesep.join(additional_information)

            missing_data_exception = ValueError(missing_data_details)

            self._communicators.error(
                message + missing_data_details,
                missing_data_exception,
                verbosity=Verbosity.NORMAL,
                publish=True
            )

            raise missing_data_exception

        self._communicators.info(
            "Finished loading prediction data",
            verbosity=Verbosity.LOUD,
            publish=True
        )

        data = observations.join(other=crosswalk_data, how="inner", on=[self._observed_location_field])

        join_left_on = [self._predicted_location_field, self._observed_xaxis]
        join_right_on = [self._predicted_location_field, self._predicted_xaxis]

        try:
            common_columns = [
                column_name
                for column_name in data.columns
                if column_name not in join_left_on
                   and column_name in predictions.columns
            ]
            data = data.join(
                other=predictions,
                how="inner",
                left_on=join_left_on,
                right_on=join_right_on,
                suffix='_prediction'
            )
            data = data.rename({
                column_name: f"{column_name}_observation"
                for column_name in common_columns
            })
        except ValueError as e:
            logging.error(str(e), stack_info=True, exc_info=e)
            raise ValueError(
                f"Can't merge data and predictions based on {str(data.schema)} to {str(predictions.schema)}, respectively"
            ) from e

        self._communicators.info(
            "Finished joining observation and prediction data",
            verbosity=Verbosity.LOUD,
            publish=True
        )

        thresholds_with_rules = [
            threshold_spec
            for threshold_spec in self._instructions.thresholds
            if bool(threshold_spec.application_rules)
        ]

        for threshold_specification in thresholds_with_rules:
            observation_rule = threshold_specification.application_rules.observation_field
            prediction_rule = threshold_specification.application_rules.prediction_field

            index_fields = []

            if observation_rule and observation_rule.name not in data.columns:
                data = data.with_columns([
                    polars.col(observation_rule.path).map_elements(observation_rule.to_datatype).alias(observation_rule.name),
                ])

                index_fields.append(observation_rule.name)

            if prediction_rule and prediction_rule.name not in data.columns:
                data = data.with_columns([
                    polars.col(prediction_rule.path).map_elements(prediction_rule.to_datatype).alias(prediction_rule.name)
                ])

                index_fields.append(prediction_rule.name)

            data = data.set_index(keys=index_fields, drop=True)

        self._communicators.info(
            "Finished applying special threshold rules to loaded values",
            verbosity=Verbosity.LOUD,
            publish=True
        )

        return data

    def normalize_values(self, data_to_evaluate: polars.DataFrame) -> polars.DataFrame:
        """
        Converts passed data into a common form for evaluation

        For example: You can't readily compare data measured in cubic meters per second to data measured in
        thousands of cubic feet per second, so they are converted into a common measurement unit

        Args:
            data_to_evaluate:
                Matched data whose rows will be compared
        Returns:
            A version of the passed `data_to_evaluate` whose observed and predicted values are ready to compare
        """
        if data_to_evaluate['unit_prediction'].equals(data_to_evaluate['unit_observation']):
            return data_to_evaluate

        data_to_evaluate = self._converter(data_to_evaluate)

        data_to_evaluate["unit_prediction"] = data_to_evaluate["unit_observation"]

        self._communicators.info(
            "Finished converting all data into a uniform measurement unit",
            verbosity=Verbosity.LOUD,
            publish=True
        )

        return data_to_evaluate

    def get_thresholds(self) -> typing.Dict[str, typing.Sequence[metrics.Threshold]]:
        """
        Generates a mapping between all locations to be evaluated and the thresholds required to do so

        Returns:
            A mapping between all locations to be evaluated and a series of thresholds used to do so
        """
        thresholds: typing.Dict[str, typing.List[metrics.Threshold]] = {}
        for threshold_definition in self._instructions.thresholds:
            found_thresholds = threshold.get_thresholds(threshold_definition)

            for location, threshold_list in found_thresholds.items():
                if location not in thresholds:
                    thresholds[location] = []
                thresholds[location].extend(threshold_list)

        return thresholds

    def score(
        self,
        data_to_evaluate: polars.DataFrame,
        thresholds: typing.Dict[str, typing.Sequence[metrics.threshold.ThresholdMetadata]]
    ) -> typing.Dict[typing.Tuple[str, str], metrics.MetricResults]:
        """
        Performs the evaluation

        Args:
            data_to_evaluate:
                The values ready to compare
            thresholds:
                The thresholds used to compare values
        Returns:
            A mapping between the locations being evaluated and the results of the metrics performed on them
        """
        scheme = self._instructions.scheme.generate_scheme(self._communicators)

        groupby_columns = [
            self._observed_location_field,
            self._predicted_location_field
        ]

        scores: typing.Dict[typing.Tuple[str, str], metrics.MetricResults] = {}

        for identifiers, group in data_to_evaluate.group_by(*groupby_columns):  # type: typing.Tuple[str, str], polars.DataFrame
            observed_location, predicted_location = identifiers     # type: str, str

            location_thresholds = thresholds.get(observed_location)

            self._communicators.info(
                f"Creating truth tables for {str(identifiers)}",
                verbosity=Verbosity.LOUD,
                publish=True
            )

            self._communicators.info(
                f"Scoring {str(identifiers)}",
                verbosity=Verbosity.LOUD,
                publish=True
            )

            if location_thresholds:
                location_scores = scheme.score(
                    group,
                    location_thresholds
                )
                scores[identifiers] = location_scores
                if self._verbosity == Verbosity.ALL:
                    data = {
                        "observed_location": observed_location,
                        "predicted_location": predicted_location,
                        "scores": location_scores.to_dict(),
                    }
                    reason = "location_scores"
                    self._communicators.write(reason=reason, data=data)

        self._communicators.info(
            "All locations have been evaluated",
            verbosity=Verbosity.LOUD,
            publish=True
        )

        return scores


def evaluate(
    definition: specification.EvaluationSpecification,
    communicators: COMMUNICATORS = None,
    verbosity: Verbosity = None
) -> specification.EvaluationResults:
    """
    Performs an evaluation

    Args:
        definition: The instructions on how to conduct the evaluation
        communicators: The communicators to use to send messages through as the evaluation goes on
        verbosity: How chatty the evaluation should be

    Returns:
        The results of the evaluation
    """
    evaluator = Evaluator(definition, communicators, verbosity)
    return evaluator.evaluate()
