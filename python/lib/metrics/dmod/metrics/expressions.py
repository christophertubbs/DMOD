"""
Defines a class that dynamically builds polars expressions for metrics
"""
from __future__ import annotations

import abc
import math
import os
import typing
import operator
import re

from math import inf as infinity

import polars
import numpy

from .scoring import ConfidenceInterval
from .scoring import create_identifier
from .scoring import Scores
from .scoring import Score
from .threshold import ThresholdMetadata
from .unit_registry import units

NUMERIC_TYPES: typing.Tuple[type, ...] = (
    int,
    float,
    polars.datatypes.classes.NumericType,
    numpy.floating,
    numpy.integer
)
"""All the different types that might be a number"""
NUMBER = typing.Union[NUMERIC_TYPES]
"""Indicates some sort of non-complex number"""

SAMPLE_SIZE_LABEL: typing.Final[str] = "sample_size"
"""The label for the column that represents the sample size for a metric value"""
SAMPLE_SIZE: polars.Expr = polars.len().alias(SAMPLE_SIZE_LABEL)
"""The formula for the sample size column"""

THRESHOLD_NAME_LABEL: typing.Final[str] = "threshold"
"""The label for the column the names the threshold that the results belong to"""

THRESHOLD_WEIGHT_LABEL: typing.Final[str] = "threshold_weight"
"""The label for the column that contains the weight of a metric's threshold"""

METRIC_WEIGHT_SUFFIX: typing.Final[str] = "_weight"
"""The suffix for the column that contains the weight of a metric"""

LOWER_BOUND_SUFFIX: typing.Final[str] = "_lower_bound"
"""The lower bound of a metric's confidence interval"""

UPPER_BOUND_SUFFIX: typing.Final[str] = "_upper_bound"
"""The upper bound of a metric's confidence interval"""

SIMULATION_EXCEEDS_LABEL: typing.Final[str] = "simulation_exceeds"
"""The name of the column saying whether or not the simulation value exceeds the given threshold"""
CONTROL_EXCEEDS_LABEL: typing.Final[str] = "control_exceeds"
"""The name of the column saying whether or not the control value exceeds the given threshold"""

SIMULATION_EXCEEDS_COLUMN: polars.Expr = polars.col(SIMULATION_EXCEEDS_LABEL)
"""The column saying whether or not the simulation value exceeds the given threshold"""
CONTROL_EXCEEDS_COLUMN: polars.Expr = polars.col(CONTROL_EXCEEDS_LABEL)
"""The column saying whether or not the control value exceeds the given threshold"""

HITS_LABEL: typing.Final[str] = "hit"
"""
The name of the column in a contingency table stating whether both the simulation and control value exceeds the 
given threshold
"""
MISSES_LABEL: typing.Final[str] = "miss"
"""
The name of the column in a contingency table stating whether the control exceeds the given threshold but the 
simulation didn't
"""
TRUE_NEGATIVE_LABEL: typing.Final[str] = "true_negative"
"""
The name of the column in a contingency table stating whether both the simulation and control value did not exceed 
the given threshold
"""
FALSE_POSITIVE_LABEL: typing.Final[str] = "false_positive"
"""
The name of the column in a contingency table stating whether the simulation exceeded the threshold but 
the control did not
"""
MEAN_CONTROL_LABEL: typing.Final[str] = "mean_control"
"""
The name of the column in a table for continuous metrics stating the mean of control values
"""
MEAN_SIMULATION_LABEL: typing.Final[str] = "mean_simulation"
"""
The name of the column in a table for continuous metrics stating the mean of simulation values
"""
COVARIANT_LABEL: typing.Final[str] = "covariant"
"""
The name of the column in a table for continuous metrics stating the covariant of control and simulated values
"""
CONTROL_STANDARD_DEVIATION_LABEL: typing.Final[str] = "control_standard_deviation"
"""
The name of the column in a table for continuous metrics stating the standard deviation of control values
"""
SIMULATION_STANDARD_DEVIATION_LABEL: typing.Final[str] = "simulation_standard_deviation"
"""
The name of the column in a table for continuous metrics stating the standard deviation of simulation values
"""
ERROR_LABEL: typing.Final[str] = "error"
"""
The name of the column showing the straight error between the control and simulated values (simulation - control)
"""
CORRELATION_LABEL: typing.Final[str] = "correlation"
"""
The name of the column showing the correlation between the control and simulated values
"""

HITS_COLUMN: polars.Expr = polars.col(HITS_LABEL)
"""The column that contains the number of hits for locations in a contingency table"""
MISSES_COLUMN: polars.Expr = polars.col(MISSES_LABEL)
"""The column that contains the number of misses for locations in a contingency table"""
TRUE_NEGATIVE_COLUMN: polars.Expr = polars.col(TRUE_NEGATIVE_LABEL)
"""The column that contains the number of true negatives for locations in a contingency table"""
FALSE_POSITIVE_COLUMN: polars.Expr = polars.col(FALSE_POSITIVE_LABEL)
"""The column that contains the number of false positives for locations in a contingency table"""
MEAN_CONTROL_COLUMN: polars.Expr = polars.col(MEAN_CONTROL_LABEL)
"""The column that contains the mean of control values"""
MEAN_SIMULATION_COLUMN: polars.Expr = polars.col(MEAN_SIMULATION_LABEL)
"""The column that contains the mean of simulation values"""
COVARIANT_COLUMN: polars.Expr = polars.col(COVARIANT_LABEL)
"""The column that contains the covariance between control and simulated values"""
CONTROL_STANDARD_DEVIATION_COLUMN: polars.Expr = polars.col(CONTROL_STANDARD_DEVIATION_LABEL)
"""The column that contains the standard deviation of control values"""
SIMULATION_STANDARD_DEVIATION_COLUMN: polars.Expr = polars.col(SIMULATION_STANDARD_DEVIATION_LABEL)
"""The column that contains the standard deviation of simulation values"""
ERROR_COLUMN: polars.Expr = polars.col(ERROR_LABEL)
"""The column that contains the error between the simulated and control values (simulation - control)"""
CORRELATION_COLUMN: polars.Expr = polars.col(CORRELATION_LABEL)
"""The column that contains the correlation between the simulated and control values"""

POSITIVE_CONTROLS_LABEL: typing.Final[str] = "positive_controls"
"""
The name of the column in a contingency table that defines the number of times that the control value fit a threshold
"""
POSITIVE_CONTROLS: polars.Expr = (HITS_COLUMN + MISSES_COLUMN).alias(POSITIVE_CONTROLS_LABEL)
"""
The expression that determines how many times the control value fit a threshold.
"""
POSITIVE_CONTROLS_COLUMN: polars.Expr = polars.col(POSITIVE_CONTROLS_LABEL)
"""
The expression that points at the column that details how many times a control value fit a threshold
"""

NEGATIVE_CONTROLS_LABEL: typing.Final[str] = "negative_controls"
"""
The name of the column in a contingency table that defines the number of times a control value did not fit a threshold
"""
NEGATIVE_CONTROLS: polars.Expr = (FALSE_POSITIVE_COLUMN + TRUE_NEGATIVE_COLUMN).alias(NEGATIVE_CONTROLS_LABEL)
"""
The expression that determines how many times the control value did not fit a threshold
"""
NEGATIVE_CONTROLS_COLUMN: polars.Expr = polars.col(NEGATIVE_CONTROLS_LABEL)
"""
The expression that points at the column that details how many times a control value did not match a threshold
"""

POSITIVE_SIMULATIONS_LABEL: typing.Final[str] = "positive_simulations"
"""
The name of the column in a contingency table that defines the number of times the simulation value fit a threshold
"""
POSITIVE_SIMULATIONS: polars.Expr = (HITS_COLUMN + FALSE_POSITIVE_COLUMN).alias(POSITIVE_SIMULATIONS_LABEL)
"""
The expression that determines how many times the simulation value fit a threshold.
"""
POSITIVE_SIMULATIONS_COLUMN: polars.Expr = polars.col(POSITIVE_SIMULATIONS_LABEL)
"""
The expression that points at the column that details how many times a simulation value fit a threshold.
"""

NEGATIVE_SIMULATIONS_LABEL: typing.Final[str] = "negative_simulations"
"""
The name of the column in a contingency table that defines the number of times a simulation value did not 
fit a threshold
"""
NEGATIVE_SIMULATIONS: polars.Expr = (MISSES_COLUMN + TRUE_NEGATIVE_COLUMN).alias(NEGATIVE_SIMULATIONS_LABEL)
"""
The expression that determines how many times a simulation value did not fit a threshold.
"""
NEGATIVE_SIMULATIONS_COLUMN: polars.Expr = polars.col(NEGATIVE_SIMULATIONS_LABEL)
"""
The expression that points at the column that details how many times a simulation value did not fit a threshold.
"""

SAMPLE_SIZE_COLUMN: polars.Expr = polars.col(SAMPLE_SIZE_LABEL)
"""
The expression that points at the column holding the sample size of the metric
"""


PHRASE_PATTERN: re.Pattern = re.compile(r"[A-Z][a-z]+(_+)?")
"""
A regular expression used to find a part of a name. For a string like 'ProbabilityOfDetection', 
`PHRASE_PATTERN.findall` should yield `['Probability', 'Of', 'Detection']`
"""

class Statement:
    def __init__(self, label: str, formula: polars.Expr = None):
        self.__label: typing.Final[str] = label
        self.__column: polars.Expr = polars.col(label)
        self.__formula: typing.Optional[polars.Expr] = formula

    @property
    def label(self) -> str:
        return self.__label

    @property
    def column(self) -> polars.Expr:
        return self.__column

    def get_formula(self, default: polars.Expr = None) -> typing.Optional[polars.Expr]:
        return self.__formula if self.__formula is not None else default

    def __str__(self):
        return self.__label


class PairTableMetadata:
    """
    A data transfer object containing indicators for a pair table, such as columns to use
    """
    def __init__(
        self,
        control_column_name: str,
        simulation_column_name: str,
        control_location_column_name: str,
        simulation_location_column_name: str,
        time_column_name: str,
        unit_name: str,
        confidence_interval: float = 0.95,
        confidence_interval_iterations: int = 1500
    ):
        self.__control_column_name: str = control_column_name
        self.__control_column = polars.col(control_column_name)

        self.__simulation_column_name: str = simulation_column_name
        self.__simulation_column = polars.col(simulation_column_name)

        self.__control_location_column_name: str = control_location_column_name
        self.__control_location_column = polars.col(control_location_column_name)

        self.__simulation_location_column_name: str = simulation_location_column_name
        self.__simulation_location_column = polars.col(simulation_location_column_name)

        self.__time_column_name: str = time_column_name
        self.__time_column = polars.col(time_column_name)

        self.__confidence_interval: float = confidence_interval
        self.__confidence_interval_iterations: int = confidence_interval_iterations
        self.__unit_name: str = unit_name

    @property
    def group_keys(self) -> typing.Tuple[str, ...]:
        """
        The name of the columns to use for grouping
        """
        return self.control_location_column_name, self.simulation_location_column_name


    @property
    def confidence_interval(self) -> float:
        """
        The percentage to use to create the confidence interval
        """
        return self.__confidence_interval

    @property
    def lower_bound_of_confidence_interval(self) -> float:
        """
        The percentile of the lower bound used to calculate the confidence interval

        Say a confidence interval of 95% is to be used. This means that the inner 95% is to be used. 100% - 95% is 5%,
        so 5% of the total data will be excluded, which will come from the lower and upper ends of the range of data.
        Since this should be evenly distributed on both ends, we divide by two. The lower bound will be that amount
        from 0% the the lower bound will be that amount away from 100%. 5% / 2.0% is 2.5%, so 2.5% will be cut from both
        ends. This means that the lower bound will be 0% + 2.5%, or just 2.5%, and the upper bound will be 100% - 2.5%,
        or 97.5%
        """
        # Find the total amount that will be excluded
        total_buffer: float = 1 - self.__confidence_interval

        # Find the amount excluded from each end
        surrounding_buffer: float = total_buffer / 2

        # Return the amount excluded from the lower end
        return surrounding_buffer

    @property
    def upper_bound_of_confidence_interval(self) -> float:
        """
        The percentile of the upper bound used to calculate the confidence interval

        Say a confidence interval of 95% is to be used. This means that the inner 95% is to be used. 100% - 95% is 5%,
        so 5% of the total data will be excluded, which will come from the lower and upper ends of the range of data.
        Since this should be evenly distributed on both ends, we divide by two. The lower bound will be that amount
        from 0% the the lower bound will be that amount away from 100%. 5% / 2.0% is 2.5%, so 2.5% will be cut from both
        ends. This means that the lower bound will be 0% + 2.5%, or just 2.5%, and the upper bound will be 100% - 2.5%,
        or 97.5%
        """
        # Find the total percentage excluded
        total_buffer: float = 1 - self.__confidence_interval

        # Find the total percentage excluded from each end
        surrounding_buffer: float = total_buffer / 2

        # Find the amount excluded from the upper end
        return 1 - surrounding_buffer

    @property
    def confidence_interval_iterations(self) -> int:
        """
        The number of times to bootstrap to create a confidence interval
        Returns:

        """
        return self.__confidence_interval_iterations
    @property
    def unit_name(self) -> str:
        """
        The name of the unit that all values are in
        """
        return self.__unit_name

    @property
    def control_location_column_name(self) -> str:
        """
        The name of the column that contains the names of the locations of the control values
        """
        return self.__control_location_column_name

    @property
    def control_location_column(self) -> polars.Expr:
        """
        The column that contains the names of locations used by the control (truth) data
        """
        return self.__control_location_column

    @property
    def simulation_location_column_name(self) -> str:
        """
        The name of the column that states the location of the simulated values
        """
        return self.__simulation_location_column_name

    @property
    def simulation_location_column(self) -> polars.Expr:
        """
        The column that contains the names of locations used by the simulation/experimental data
        """
        return self.__simulation_location_column

    @property
    def time_column_name(self) -> str:
        """
        The name of the column that contains information about when values took place
        """
        return self.__time_column_name

    @property
    def time_column(self) -> polars.Expr:
        """
        The column that contains information about when values took place
        """
        return self.__time_column

    @property
    def control_column_name(self) -> str:
        """
        The name of the column that contains the control values
        """
        return self.__control_column_name

    @property
    def control_column(self) -> polars.Expr:
        """
        The column that contains the control (truth) values
        """
        return self.__control_column

    @property
    def simulation_column_name(self) -> str:
        """
        The name of the column that contains the simulation/experimental values
        """
        return self.__simulation_column_name

    @property
    def simulation_column(self) -> polars.Expr:
        """
        The column that contains the simulation/experimental values
        """
        return self.__simulation_column


class MetricExpression(abc.ABC):
    """
    An item that may evaluate a metric on polars dataframes through the use of polars expressions
    """
    @classmethod
    def related_metrics(cls) -> typing.Sequence[typing.Type[MetricExpression]]:
        """
        Metrics that should be considered if this is to be used
        """
        return []

    @classmethod
    def tags(cls) -> typing.Sequence[str]:
        """
        General identifiers that can help classify the use of this metric
        """
        return []

    @classmethod
    @abc.abstractmethod
    def get_description(cls):
        """A description of the metric and how to interpret it"""

    @classmethod
    def get_name(cls) -> str:
        """The name of the metric"""
        return ' '.join(match.group().strip('_').strip() for match in PHRASE_PATTERN.finditer(cls.__name__))

    @property
    def expected_schema(self) -> typing.Dict[str, polars.datatypes.DataTypeClass]:
        """The minimum schema that the input data must conform to"""
        return {
            self.table_metadata.control_column_name: polars.datatypes.classes.FloatType,
            self.table_metadata.simulation_column_name: polars.datatypes.classes.FloatType,
            **{key: polars.datatypes.DataType for key in self.table_metadata.group_keys}
        }

    @classmethod
    def is_categorical(cls) -> bool:
        """
        Indicates whether this is a categorical metric

        Categorical metrics operate upon contingency tables, not time series

        A categorical metric takes input that looks like:

        +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+
        | control_location | simulation_location | hit | miss | false_positive | true_negative | positive_controls | negative_controls | positive_simulation | negative_simulation | sample_size |
        +==================+=====================+=====+======+================+===============+===================+===================+=====================+=====================+=============+
        | location 0       | Site 0              | 15  | 455  | 17             | 888           | 470               | 905               | 32                  | 1343                | 1375        |
        +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+
        | location 1       | Site 1              | 17  | 322  | 84             | 972           | 339               | 1056              | 101                 | 1294                | 1395        |
        +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+
        | location 1       | Site 1a             | 32  | 105  | 12             | 1300          | 137               | 1312              | 44                  | 1305                | 1349        |
        +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+
        | ...              | ...                 | ... | ...  | ...            | ...           | ...               | ...               | ...                 | ...                 | ...         |
        +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+
        | location N       | Site N              | 72  | 18   | 1576           | 200           | 90                | 1776              | 1648                | 218                 | 1866        |
        +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+

        and non-categorical metrics operate upon time series that look like:

        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
        | datetime            | control_location | control | simulation_location | simulation | threshold_0 | threshold_1 | control_exceeds | simulation_exceeds |
        +=====================+==================+=========+=====================+============+=============+=============+=================+====================+
        | 1970-01-01 00:00:00 | location 0       | 3.14    | Site 0              | 4.55       | 4           | 7           | False           | True               |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
        | 1970-01-01 01:00:00 | location 0       | 3.78    | Site 0              | 4.24       | 4           | 7           | False           | True               |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
        | ...                 | ...              | ...     | ...                 | ...        | ...         | ...         | ...             | ...                |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
        | 1975-12-31 23:00:00 | location N       | 4586    | Site N              | 4555       | 3000        | 8000        | True            | True               |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
        """
        return False

    def __init__(
        self,
        table_metadata: PairTableMetadata,
        weight: NUMBER,
        lower_bound: NUMBER = -infinity,
        upper_bound: NUMBER = infinity,
        ideal_value: NUMBER = numpy.nan,
        failure: NUMBER = None,
        greater_is_better: bool = True
    ):
        """
        Constructor

        Args:
            table_metadata: An object describing how to interpret the given dataframes
            weight: The relative, numeric significance of the metric itself
            lower_bound: The lowest acknowledged value - this doesn't necessarily need to be the lower bound of the statistical function
            upper_bound: The highest acknowledged value - this doesn't necessarily need to be the upper bound of the statistical function
            ideal_value: The value deemed to be perfect for the metric
            failure: A value indicating a complete failure for the metric, triggering a failure among all accompanying metrics
            greater_is_better: Whether a higher value is preferred over a lower value
        """
        if weight is None or not isinstance(weight, NUMERIC_TYPES) or numpy.isnan(weight):
            raise ValueError("Weight must be supplied and must be numeric")

        self.__table_metadata: PairTableMetadata = table_metadata
        self.__lower_bound = lower_bound if lower_bound is not None else -infinity
        self.__upper_bound = upper_bound if upper_bound is not None else infinity
        self.__ideal_value = ideal_value if ideal_value is not None else numpy.nan
        self.__weight = weight
        self.__greater_is_better = greater_is_better if greater_is_better is not None else True
        self.__failure = failure

    @classmethod
    def get_identifier(cls) -> str:
        """
        Returns an identifier that may be compared against other strings for identification

        This will convert "Pearson Correlation Coefficient" to "pearsoncorrelationcoefficient"

        If a function tries to find a metric by name, it can compare and find the metric with values like
        "pEArSoNcOrreLaTionC oeffIcIEnT" or "pearson correlation_coefficient"

        Returns:
            An identifier that may be compared against other strings for identification
        """
        return create_identifier(cls.get_name())

    @property
    def name(self) -> str:
        """
        Returns:
            The name of the metric
        """
        return self.get_name()

    @property
    def table_metadata(self) -> PairTableMetadata:
        """
        An object describing how to interpret the given dataframes
        """
        return self.__table_metadata

    @property
    def fails_on(self) -> NUMBER:
        """
        Returns:
            The value that might trigger a failing evaluation
        """
        return self.__failure

    @property
    def weight(self) -> NUMBER:
        """
        Returns:
            The relative numeric significance of the metric
        """
        return self.__weight

    @property
    def ideal_value(self) -> NUMBER:
        """
        Returns:
            The perfect value
        """
        return self.__ideal_value

    @property
    def lower_bound(self) -> NUMBER:
        """
        The lowest possible value to consider when scaling the result

        NOTE: While the lower and upper bound generally correspond to the upper and lower bound of the metric,
              the lower bound on this corresponds to the lowers number that has any affect on the scaling process.
              For instance, a metric might have a bounds of [-1, 1], but we only want to consider [0, 1] for scoring
              purposes, where anything under 0 is translated as 0

        Returns:
            The lowest value to consider when scaling
        """
        return self.__lower_bound

    @property
    def upper_bound(self) -> NUMBER:
        """
        The highest possible value to consider when scaling the result

        NOTE: While the lower and upper bound generally correspond to the upper and lower bound of the metric,
              the lower bound on this corresponds to the lowers number that has any affect on the scaling process.
              For instance, a metric might have a bounds of [-1, 1], but we only want to consider [0, 1] for scoring
              purposes, where anything under 0 is translated as 0

        Returns:
            The highest value to consider when scaling
        """
        return self.__upper_bound

    @property
    def greater_is_better(self) -> bool:
        """
        Returns:
            Whether a greater value is considered better
        """
        return self.__greater_is_better

    @property
    def has_upper_bound(self) -> bool:
        """Whether this metric has a defined upper bound"""
        return not numpy.isnan(self.__upper_bound) and self.__upper_bound < infinity

    @property
    def has_lower_bound(self) -> bool:
        """Whether this metric has a defined lower bound"""
        return not numpy.isnan(self.__lower_bound) and self.__lower_bound > -infinity

    @property
    def has_ideal_value(self) -> bool:
        """Whether this metric has a value that is considered perfect"""
        return self.__ideal_value is not None and \
               not numpy.isnan(self.__ideal_value) and \
               not numpy.isinf(self.__ideal_value)

    @property
    def fully_bounded(self) -> bool:
        """Whether this metric has both an upper and lower bound"""
        return self.has_lower_bound and self.has_upper_bound

    @property
    def partially_bounded(self) -> bool:
        """Whether this metric has a lower bound but not an upper bound or vice versa"""
        return self.has_lower_bound ^ self.has_upper_bound

    @property
    def bounded(self) -> bool:
        """Whether this metric is has an upper or lower bound"""
        return self.has_lower_bound or self.has_upper_bound

    def validate_operation_result_schema(self, data: polars.DataFrame) -> None:
        """
        Ensure that the data coming out of the metric operation is of the correct format

        Raises an exception if the schema is incorrect

        Args:
            data: The data produced via `_operate_on_frame`
        """
        expected_schema: typing.Mapping[str, polars.datatypes.classes.DataTypeClass] = {
            SAMPLE_SIZE_LABEL: polars.datatypes.classes.IntegerType,
            self.get_identifier(): polars.datatypes.classes.FloatType,
            **{key: polars.datatypes.classes.DataType for key in self.table_metadata.group_keys}
        }
        validate_partial_schema(data=data, required_schema=expected_schema)

    def preprocess_input(self, data: polars.DataFrame, threshold: ThresholdMetadata) -> polars.DataFrame:
        """
        Alter input data to make calculations more efficient or of the desired shape and schema

        Args:
            data: The data that serves as the input for the metric
            threshold: The threshold for the metric being performed

        Returns:
            The processed input data
        """
        return data

    def evaluate(self, data: polars.DataFrame, threshold: ThresholdMetadata) -> typing.Sequence[Score]:
        """
        Validates the input data and calls the implementation of the evaluation logic


        For an input dataframe like:

        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
        | datetime            | control_location | control | simulation_location | simulation | threshold_0 | threshold_1 |
        +=====================+==================+=========+=====================+============+=============+=============+
        | 1970-01-01 00:00:00 | location 0       | 5.14    | Site 0              | 4.55       | 4           | 7           |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
        | 1970-01-01 01:00:00 | location 0       | 3.78    | Site 0              | 4.24       | 4           | 7           |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
        | ...                 | ...              | ...     | ...                 | ...        | ...         | ...         |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
        | 1975-12-31 23:59:00 | location N       | 4586    | Site N              | 4555       | 3000        | 8000        |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+

        length = 5,196,000

        evaluate(data, "threshold_0") will yield something like:

        +------------------+---------------------+----------------+----------------+----------------------------+
        | control_location | simulation_location | threshold_name | example_metric | example_metric_sample_size |
        +==================+=====================+================+================+============================+
        | location 0       | Site 0              | threshold_0    | 0.92           | 6495                       |
        +------------------+---------------------+----------------+----------------+----------------------------+
        | location 1       | Site 1              | threshold_0    | 0.85           | 6495                       |
        +------------------+---------------------+----------------+----------------+----------------------------+
        | ...              | ...                 | ...            | ...            | ...                        |
        +------------------+---------------------+----------------+----------------+----------------------------+
        | location N       | Site N              | threshold_0    | 0.99           | 6495                       |
        +------------------+---------------------+----------------+----------------+----------------------------+

        length = 800

        Args:
            data: The metric to evaluate
            threshold: Information about the threshold to be used

        Returns:
            A new dataframe with columns for each location for the control and simulation values, one for the metric
                results, the name of the threshold the results are valid for, and
        """
        identifier = self.get_identifier()
        metric_column: polars.Expr = polars.col(identifier)

        data = self.preprocess_input(data=data, threshold=threshold)

        validate_partial_schema(data=data, required_schema=self.expected_schema)
        data = data.drop([column for column in data.columns if column not in self.expected_schema])

        result = self._operate_on_frame(data=data)

        self.validate_operation_result_schema(data=result)

        all_resampled_results: typing.List[polars.Dataframe] = []

        # Now build the confidence interval
        for _ in range(self.table_metadata.confidence_interval_iterations):
            resampled_data = data.sample(n=len(data), with_replacement=True)
            resampled_result = self._operate_on_frame(data=resampled_data)
            all_resampled_results.append(resampled_result)

        if all_resampled_results is not None:
            resampled_results = polars.concat(all_resampled_results)
            resampled_results = resampled_results.group_by(
                self.table_metadata.group_keys
            ).agg(
                metric_column.quantile(
                    self.table_metadata.lower_bound_of_confidence_interval
                ).alias(f"{identifier}{LOWER_BOUND_SUFFIX}"),
                metric_column.quantile(
                    self.table_metadata.upper_bound_of_confidence_interval
                ).alias(f"{identifier}{UPPER_BOUND_SUFFIX}")
            )
            result = result.join(resampled_results, how='inner', on=self.table_metadata.group_keys)

        individual_scores: typing.List[Score] = [
            Score(
                self,
                value=parameters[identifier],
                threshold=threshold,
                control_location=parameters[self.table_metadata.control_location_column_name],
                simulation_location=parameters[self.table_metadata.simulation_location_column_name],
                sample_size=parameters[SAMPLE_SIZE_LABEL],
                confidence_interval=ConfidenceInterval(
                    confidence=self.table_metadata.confidence_interval,
                    lower_bound=parameters.get(f"{identifier}{LOWER_BOUND_SUFFIX}"),
                    upper_bound=parameters.get(f"{identifier}{UPPER_BOUND_SUFFIX}"),
                )
            )
            for parameters in result.to_dicts()
        ]

        return individual_scores

    @abc.abstractmethod
    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        """
        The implementation of the metric logic


        For an input dataframe like:

        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
        | datetime            | control_location | control | simulation_location | simulation | threshold_0 | threshold_1 |
        +=====================+==================+=========+=====================+============+=============+=============+
        | 1970-01-01 00:00:00 | location 0       | 5.14    | Site 0              | 4.55       | 4           | 7           |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
        | 1970-01-01 01:00:00 | location 0       | 3.78    | Site 0              | 4.24       | 4           | 7           |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
        | ...                 | ...              | ...     | ...                 | ...        | ...         | ...         |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
        | 1975-12-31 23:59:00 | location N       | 4586    | Site N              | 4555       | 3000        | 8000        |
        +---------------------+------------------+---------+---------------------+------------+-------------+-------------+

        length = 5,196,000

        evaluate(data, "threshold_0") will yield something like:

        +------------------+---------------------+----------------+----------------+----------------------------+
        | control_location | simulation_location | threshold_name | example_metric | example_metric_sample_size |
        +==================+=====================+================+================+============================+
        | location 0       | Site 0              | threshold_0    | 0.92           | 6495                       |
        +------------------+---------------------+----------------+----------------+----------------------------+
        | location 1       | Site 1              | threshold_0    | 0.85           | 6495                       |
        +------------------+---------------------+----------------+----------------+----------------------------+
        | ...              | ...                 | ...            | ...            | ...                        |
        +------------------+---------------------+----------------+----------------+----------------------------+
        | location N       | Site N              | threshold_0    | 0.99           | 6495                       |
        +------------------+---------------------+----------------+----------------+----------------------------+

        length = 800

        Args:
            data: The metric to evaluate

        Returns:
            A new dataframe with columns for each location for the control and simulation values, one for the metric
                results, the name of the threshold the results are valid for, and
        """

    def __str__(self):
        return self.get_name()


class ContinuousExpression(MetricExpression, abc.ABC):
    """
    Base class for continuous metrics that include common function implementations
    """
    def preprocess_input(self, data: polars.DataFrame, threshold: ThresholdMetadata) -> polars.DataFrame:
        if validate_partial_schema(data=data, required_schema=self.expected_schema, throw=False):
            data = data.with_columns(
                (self.table_metadata.simulation_column - self.table_metadata.control_column).alias(ERROR_LABEL),
            )
            statistics: polars.DataFrame = data.group_by(self.table_metadata.group_keys).agg(
                self.table_metadata.control_column.mean().alias(MEAN_CONTROL_LABEL),
                self.table_metadata.simulation_column.mean().alias(MEAN_SIMULATION_LABEL),
                polars.cov(self.table_metadata.simulation_column, self.table_metadata.control_column).alias(COVARIANT_LABEL),
                self.table_metadata.control_column.std().alias(CONTROL_STANDARD_DEVIATION_LABEL),
                self.table_metadata.simulation_column.std().alias(SIMULATION_STANDARD_DEVIATION_LABEL),
                polars.corr(self.table_metadata.control_column, self.table_metadata.simulation_column).alias(CORRELATION_LABEL),
            )
            # join is used instead of 'with_columns' since the values are aggregates
            data = data.join(statistics, on=self.table_metadata.group_keys)
        return data

    @property
    def expected_schema(self) -> typing.Dict[str, polars.datatypes.DataTypeClass]:
        schema: typing.Dict[str, polars.datatypes.DataTypeClass] = super().expected_schema
        schema.update({
            MEAN_CONTROL_LABEL: polars.datatypes.classes.FloatType,
            MEAN_SIMULATION_LABEL: polars.datatypes.classes.FloatType,
            CONTROL_STANDARD_DEVIATION_LABEL: polars.datatypes.classes.FloatType,
            SIMULATION_STANDARD_DEVIATION_LABEL: polars.datatypes.classes.FloatType,
            ERROR_LABEL: polars.datatypes.classes.FloatType,
            COVARIANT_LABEL: polars.datatypes.classes.FloatType,
            CORRELATION_LABEL: polars.datatypes.classes.FloatType,
        })
        return schema


class CategoricalExpression(MetricExpression, abc.ABC):
    """
    Base class for expressions for categorical metrics that include common function implementations
    """
    @classmethod
    def is_categorical(cls) -> bool:
        return True

    @property
    def expected_schema(self) -> typing.Dict[str, polars.datatypes.DataTypeClass]:
        return {
            HITS_LABEL: polars.datatypes.IntegerType,
            MISSES_LABEL: polars.datatypes.IntegerType,
            FALSE_POSITIVE_LABEL: polars.datatypes.IntegerType,
            TRUE_NEGATIVE_LABEL: polars.datatypes.IntegerType,
            POSITIVE_SIMULATIONS_LABEL: polars.datatypes.IntegerType,
            NEGATIVE_SIMULATIONS_LABEL: polars.datatypes.IntegerType,
            POSITIVE_CONTROLS_LABEL: polars.datatypes.IntegerType,
            NEGATIVE_CONTROLS_LABEL: polars.datatypes.IntegerType,
            SAMPLE_SIZE_LABEL: polars.datatypes.IntegerType,
            **{key: polars.datatypes.DataType for key in self.table_metadata.group_keys}
        }

    def preprocess_input(self, data: polars.DataFrame, threshold: ThresholdMetadata) -> polars.DataFrame:
        # If this isn't a contingency table but may become one, turn it into one
        if can_become_contingency_table(data, self.table_metadata, threshold.name):
            data = mark_exceedence(table_metadata=self.table_metadata, data=data, threshold_column_name=threshold.name)
            data = create_contingency_table(table_metadata=self.table_metadata, data=data)
        return data


class ProbabilityOfDetection(CategoricalExpression):
    """
    Answers the question: What fraction of the observed "yes" events were correctly forecast?

    Range: 0 to 1.  Perfect score: 1.

    Characteristics: Sensitive to hits, but ignores false alarms. Very sensitive to the climatological frequency of
    the event. Good for rare events. Can be artificially improved by issuing more "yes" forecasts to increase the
    number of hits. Should be used in conjunction with the false alarm ratio (below). POD is also an important
    component of the Relative Operating Characteristic (ROC) used widely for probabilistic forecasts.

    References:
        Centre for Australian Weather and Climate Research (CAWCR). (n.d.). Verification methods.
        Retrieved from https://www.cawcr.gov.au/projects/verification/
    """
    @classmethod
    def get_description(cls):
        return (
            "The probability that something was detected. Sensitive to hits, but ignores false alarms. "
            "Very sensitive to the climatological frequency of the event. Good for rare events."
        )

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=1,
            failure=0.0
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier: str = self.get_identifier()
        intermediate_values: polars.DataFrame = data.with_columns(
            polars.when(POSITIVE_CONTROLS == 0)
                .then(math.nan)
                .otherwise(HITS_COLUMN / POSITIVE_CONTROLS)
                .alias(identifier)
        )

        return intermediate_values


class FalseAlarmRatio(CategoricalExpression):
    """


    References:
        Centre for Australian Weather and Climate Research (CAWCR). (n.d.). Verification methods.
        Retrieved from https://www.cawcr.gov.au/projects/verification/
    """
    @classmethod
    def get_description(cls):
        return (
            "The probability that something was falsely reported as happening. Sensitive to false alarms, "
            "but ignores misses. Very sensitive to the climatological frequency of the event. "
            "Should be used in conjunction with the probability of detection."
        )

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=0,
            failure=1.0,
            greater_is_better=False
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier: str = self.get_identifier()
        intermediate_values: polars.DataFrame = data.with_columns(
            polars.when(
                (POSITIVE_SIMULATIONS_COLUMN == 0) & FALSE_POSITIVE_COLUMN.eq(0)
            )
            .then(0)
            .when(POSITIVE_SIMULATIONS_COLUMN == 0)
            .then(math.nan)
            .otherwise(FALSE_POSITIVE_COLUMN / (HITS_COLUMN + FALSE_POSITIVE_COLUMN))
            .alias(identifier)
        )

        return intermediate_values


class ProbabilityOfFalseDetection(CategoricalExpression):
    """


    References:
        Centre for Australian Weather and Climate Research (CAWCR). (n.d.). Verification methods.
        Retrieved from https://www.cawcr.gov.au/projects/verification/
    """
    @classmethod
    def get_description(cls):
        return (
            "What fraction of the observed 'no' events were incorrectly forecast as 'yes'. Sensitive to false alarms, "
            "but ignores misses. Can be artificially improved by issuing fewer 'yes' "
            "forecasts to reduce the number of false alarms. Not often reported for deterministic forecasts, "
            "but is an important component of the Relative Operating Characteristic (ROC) used widely for "
            "probabilistic forecasts."
        )

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=0,
            failure=1.0,
            greater_is_better=False
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier: str = self.get_identifier()

        top = FALSE_POSITIVE_COLUMN
        bottom = TRUE_NEGATIVE_COLUMN.add(FALSE_POSITIVE_COLUMN)
        intermediate_values: polars.DataFrame = data.with_columns(
            polars.when(
                (bottom == 0) & (top == 0)
            )
            .then(0)
            .when(bottom == 0)
            .then(math.nan)
            .otherwise(top / bottom)
            .alias(identifier)
        )

        return intermediate_values


class FrequencyBias(CategoricalExpression):
    """


    References:
        Centre for Australian Weather and Climate Research (CAWCR). (n.d.). Verification methods.
        Retrieved from https://www.cawcr.gov.au/projects/verification/
    """
    @classmethod
    def get_description(cls):
        return (
            "Measures the ratio of the frequency of forecast events to the frequency of observed events. "
            "Indicates whether the forecast system has a tendency to underforecast (BIAS<1) or overforecast (BIAS>1)"
        )

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=infinity,
            ideal_value=1,
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier: str = self.get_identifier()

        top = POSITIVE_SIMULATIONS_COLUMN
        bottom = POSITIVE_CONTROLS_COLUMN

        intermediate_values: polars.DataFrame = data.with_columns(
            (top/bottom).alias(identifier)
        )

        # If it tries to divide by 0, the value becomes infinity. Replace that with NaN
        intermediate_values = intermediate_values.with_columns(
            polars.when(polars.col(identifier) == infinity).then(math.nan).otherwise(polars.col(identifier))
        )

        return intermediate_values


class Accuracy(CategoricalExpression):
    """


    References:
        Centre for Australian Weather and Climate Research (CAWCR). (n.d.). Verification methods.
        Retrieved from https://www.cawcr.gov.au/projects/verification/
    """
    @classmethod
    def get_description(cls):
        return (
            'Overall, what fraction of the forecasts were correct? Can be misleading since it is heavily influenced '
            'by the most common category, usually "no event" in the case of rare weather.'
        )

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=1,
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier: str = self.get_identifier()
        top = HITS_COLUMN + TRUE_NEGATIVE_COLUMN
        bottom = polars.col(SAMPLE_SIZE_LABEL)

        intermediate_values: polars.DataFrame = data.with_columns(
            polars.when(bottom == 0)
            .then(math.nan)
            .otherwise(top / bottom)
            .alias(identifier)
        )

        return intermediate_values


class CriticalSuccessIndex(CategoricalExpression):
    """


    References:
        Centre for Australian Weather and Climate Research (CAWCR). (n.d.). Verification methods.
        Retrieved from https://www.cawcr.gov.au/projects/verification/
    """
    @classmethod
    def get_description(cls):
        return (
            'How well did the forecast "yes" events correspond to the observed "yes" events? It can be thought '
            'of as the accuracy when correct negatives have been removed from consideration, that is, TS is only '
            'concerned with forecasts that count. Sensitive to hits, penalizes both misses and false alarms.'
        )

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=1,
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier: str = self.get_identifier()
        top = HITS_COLUMN
        bottom = HITS_COLUMN + MISSES_COLUMN + FALSE_POSITIVE_COLUMN

        intermediate_values: polars.DataFrame = data.with_columns(
            polars.when(bottom == 0)
            .then(math.nan)
            .otherwise(top / bottom)
            .alias(identifier)
        )

        return intermediate_values


class EquitableThreatScore(CategoricalExpression):
    """


    References:
        Centre for Australian Weather and Climate Research (CAWCR). (n.d.). Verification methods.
        Retrieved from https://www.cawcr.gov.au/projects/verification/
    """
    @classmethod
    def get_description(cls):
        return (
            'How well did the forecast "yes" events correspond to the observed "yes" events '
            '(accounting for hits due to chance)? Sensitive to hits. Because it penalises both misses and false '
            'alarms in the same way, it does not distinguish the source of forecast error.'
        )

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=1,
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier: str = self.get_identifier()
        random_hit_label: str = "random_hits"
        random_hits_column: polars.Expr = polars.col(random_hit_label)

        random_hits = ((HITS_COLUMN + MISSES_COLUMN) * (HITS_COLUMN + FALSE_POSITIVE_COLUMN)) / SAMPLE_SIZE_COLUMN
        data = data.with_columns(
            random_hits.alias(random_hit_label)
        ).with_columns(
            polars.when(random_hits_column == infinity).then(math.nan).otherwise(random_hits_column)
        )

        top = HITS_COLUMN - random_hits_column
        bottom = HITS_COLUMN + MISSES_COLUMN + FALSE_POSITIVE_COLUMN - random_hits_column

        intermediate_values: polars.DataFrame = data.with_columns(
            polars.when((bottom == 0) | (top == 0))
            .then(math.nan)
            .when(bottom == top)
            .then(1.0)
            .otherwise(top / bottom)
            .alias(identifier)
        )

        return intermediate_values


class GeneralSkill(CategoricalExpression):
    """


    References:
        Centre for Australian Weather and Climate Research (CAWCR). (n.d.). Verification methods.
        Retrieved from https://www.cawcr.gov.au/projects/verification/
    """
    @classmethod
    def get_description(cls):
        return 'What was the accuracy of the forecast relative to that of random chance?'

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=1,
            failure=0.0
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier: str = self.get_identifier()
        metric_column: polars.Expr = polars.col(identifier)

        top = ((HITS_COLUMN * TRUE_NEGATIVE_COLUMN) - (MISSES_COLUMN * FALSE_POSITIVE_COLUMN)) * 2
        bottom = (HITS_COLUMN + MISSES_COLUMN) * (MISSES_COLUMN + TRUE_NEGATIVE_COLUMN)
        bottom = bottom + (HITS_COLUMN + FALSE_POSITIVE_COLUMN) * (FALSE_POSITIVE_COLUMN + TRUE_NEGATIVE_COLUMN)

        intermediate_values: polars.DataFrame = data.with_columns(
            (top / bottom).alias(identifier)
        ).with_columns(
            polars.when(metric_column == infinity).then(math.nan).otherwise(metric_column)
        )

        return intermediate_values


class Precision(CategoricalExpression):
    """
    Also known as the 'Success Ratio'

    Answers the question: What fraction of the forecast "yes" events were correctly observed?

    Range: 0 to 1.  Perfect score: 1.

    Characteristics: Gives information about the likelihood of an observed event, given that it was forecast.
    It is sensitive to false alarms but ignores misses. SR is equal to 1-FAR.

    References:
        Centre for Australian Weather and Climate Research (CAWCR). (n.d.). Verification methods.
        Retrieved from https://www.cawcr.gov.au/projects/verification/
    """
    @classmethod
    def get_description(cls):
        return (
            'The ratio of the number of times predictions correctly predicted an event to the total number of '
            'times the predictions stated there would be an event.'
        )

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=1
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier: str = self.get_identifier()
        metric_column: polars.Expr = polars.col(identifier)

        intermediate_values: polars.DataFrame = data.with_columns(
            (HITS_COLUMN / POSITIVE_SIMULATIONS).alias(identifier)
        ).with_columns(
            polars.when(metric_column == infinity).then(math.nan).otherwise(metric_column)
        )

        return intermediate_values


class PearsonCorrelationCoefficient(ContinuousExpression):
    """
    Addresses the question: How well did the forecast values correspond to the observed values?

    Range: -1 to 1.  Perfect score: 1.

    Characteristics: Good measure of linear association or phase error. Visually, the correlation measures how
    close the points of a scatter plot are to a straight line. Does not take forecast bias into account -- it is
    possible for a forecast with large errors to still have a good correlation coefficient with the observations.
    Sensitive to outliers.

    References:
        Centre for Australian Weather and Climate Research (CAWCR). (n.d.). Verification methods.
        Retrieved from https://www.cawcr.gov.au/projects/verification/
    """

    @classmethod
    def get_description(cls):
        return "A measure of linear correlation between two sets of data"

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        """
        Constructor

        Args:
            table_metadata: An object describing how to interpret the given dataframes
            weight: The relative significance of the metric
        """
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=1,
            failure=0.0
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier = self.get_identifier()

        result: polars.DataFrame = data.group_by(
            self.table_metadata.group_keys
        ).agg(
            CORRELATION_COLUMN.first().alias(identifier),
            polars.len().alias(SAMPLE_SIZE_LABEL)
        )

        return result


class KlingGuptaEfficiency(ContinuousExpression):
    """
    A goodness-of-fit measure providing a diagnostically interesting decomposition of the Nash-Sutcliffe efficiency

    The KGE combines three statistical metrics:

    - correlation coefficient
    - variability ratio
    - bias ratio

    into a single measure of model performance. The KGE ranges between -infinity and 1, where a value of 1 indicates
    perfect agreement between the model predictions and the observed data.
    """
    @classmethod
    def get_description(cls):
        return "A goodness-of-fit measure providing a diagnostically interesting decomposition of the " \
               "Nash-Sutcliffe efficiency"

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        """
        Constructor

        Args:
            table_metadata: An object describing how to interpret the given dataframes
            weight: The relative significance of the metric
        """
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=1
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier = self.get_identifier()

        beta_label: str = "beta"
        beta_column = polars.col(beta_label)

        gamma_label: str = "gamma"
        gamma_column = polars.col(gamma_label)

        kge: polars.Expr = (
                1 - ((CORRELATION_COLUMN - 1)**2 + (beta_column - 1)**2 + (gamma_column - 1)**2).sqrt()
        ).alias(identifier)

        intermediary_data: polars.DataFrame = data.with_columns(
            (MEAN_SIMULATION_COLUMN / MEAN_CONTROL_COLUMN).alias(beta_label),
            (SIMULATION_STANDARD_DEVIATION_COLUMN / CONTROL_STANDARD_DEVIATION_COLUMN).alias(gamma_label)
        )
        intermediary_data = intermediary_data.with_columns(
            kge
        )

        return intermediary_data.group_by(
            *self.table_metadata.group_keys, identifier
        ).agg(SAMPLE_SIZE)


class VolumeError(ContinuousExpression):
    """
    The difference between the observed volume and the predicted volume
    """
    @classmethod
    def get_description(cls):
        return "The difference between the observed volume and the predicted volume"

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        """
        Constructor

        Args:
            table_metadata: An object describing how to interpret the given dataframes
            weight: The relative significance of the metric
        """
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            ideal_value=0,
            greater_is_better=False
        )

    @property
    def expected_schema(self) -> typing.Dict[str, polars.datatypes.DataTypeClass]:
        schema: typing.Dict[str, polars.DataTypeClass] = super().expected_schema
        schema.update({
            self.table_metadata.time_column_name: polars.datatypes.classes.Datetime
        })
        return schema

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        if not isinstance(data[self.table_metadata.time_column_name].dtype, polars.datatypes.classes.NumericType):
            data = normalize_time(table_metadata=self.table_metadata, data=data)

        identifier = self.get_identifier()

        area_under_control_label = "area_under_control"
        area_under_control_column = polars.col(area_under_control_label)

        # Find the area under the control curve through the use of the trapezoidal rule. Numpy provides the means
        #   to perform this, but is not optimized for polars, so the approach has been mutated to operate as
        #   intended here.
        #
        #   (column + column.shift(-1)) will add each value to its next value and (column.shift(-1) - column)
        #       will subtract the current value from the next value
        #
        # Base on `numpy.trapezoid` (https://github.com/numpy/numpy/blob/main/numpy/lib/_function_base_impl.py)
        #   which is used by  `sklearn.metrics.auc`
        #   (https://github.com/scikit-learn/scikit-learn/blob/219eedcb5/sklearn/metrics/_ranking.py)
        area_under_control: polars.Expr = (
            0.5 * (
                self.table_metadata.control_column + self.table_metadata.control_column.shift(-1)
            ) * (
                self.table_metadata.time_column.shift(-1) - self.table_metadata.time_column
            )
        ).sum().alias(area_under_control_label)

        area_under_simulation_label = "area_under_simulation"

        # Find the area under the control curve through the use of the trapezoidal rule. Numpy provides the means
        #   to perform this, but is not optimized for polars, so the approach has been mutated to operate as
        #   intended here.
        #
        #   (column + column.shift(-1)) will add each value to its next value and (column.shift(-1) - column)
        #       will subtract the current value from the next value
        #
        # Base on `numpy.trapezoid` (https://github.com/numpy/numpy/blob/main/numpy/lib/_function_base_impl.py)
        #   which is used by  `sklearn.metrics.auc`
        #   (https://github.com/scikit-learn/scikit-learn/blob/219eedcb5/sklearn/metrics/_ranking.py)
        area_under_simulation: polars.Expr = (
            0.5 * (
                self.table_metadata.simulation_column + self.table_metadata.simulation_column.shift(-1)
            ) * (
                self.table_metadata.time_column.shift(-1) - self.table_metadata.time_column
            )
        ).sum().alias(area_under_simulation_label)
        area_under_simulation_column = polars.col(area_under_simulation_label)

        result: polars.DataFrame = data.group_by(
            self.table_metadata.group_keys
        ).agg(
            area_under_control,
            area_under_simulation,
            SAMPLE_SIZE,
        )

        result = result.with_columns(
            area_under_control_column.sub(area_under_simulation_column).abs().alias(identifier)
        )

        return result


class NormalizedNashSutcliffeEfficiency(ContinuousExpression):
    """
    The means for calculating the Normalized Nash Sutcliffe Efficiency metric.

    https://en.wikipedia.org/wiki/Nash%E2%80%93Sutcliffe_model_efficiency_coefficient
    """
    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier = self.get_identifier()

        numerator: polars.Expr = (
            (
                self.table_metadata.control_column - self.table_metadata.simulation_column
            )**2
        ).sum()
        denominator = (
            (
                self.table_metadata.control_column - MEAN_CONTROL_COLUMN
            )**2
        ).sum()

        nash_sutcliffe_efficiency = 1 - (numerator / denominator)
        normalized_nash_sutcliffe_efficiency = (1 / (2 - nash_sutcliffe_efficiency)).alias(identifier)

        result: polars.DataFrame = data.group_by(
            self.table_metadata.group_keys
        ).agg(
            normalized_nash_sutcliffe_efficiency,
            SAMPLE_SIZE,
        )

        return result

    @classmethod
    def get_description(cls):
        return "A normalized statistic that measures the relative magnitude of noise compared to information"

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        """
        Constructor

        Args:
            table_metadata: An object describing how to interpret the given dataframes
            weight: The relative significance of the metric
        """
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0,
            upper_bound=1,
            ideal_value=1
        )


class LinearTemporalTrendAbsoluteError(ContinuousExpression):
    """
    A measure of how performance changes over time. A positive result means that the data generally worsened
    over time, 0 means it was consistently right or wrong, and a negative value indicates that values
    improved over time. This has more value on shorter time periods than longer time periods. May be
    invalidated by time series with many outliers or long stretches with no activity.
    """
    @classmethod
    def get_description(cls):
        return (
            "A measure of how performance changes over time. A positive result means that the data generally worsened "
            "over time, 0 means it was consistently right or wrong, and a negative value indicates that values "
            "improved over time. This has more value on shorter time periods than longer time periods. May be "
            "invalidated by time series with many outliers."
        )

    def __init__(self, table_metadata: PairTableMetadata, weight: NUMBER):
        """
        Constructor

        Args:
            table_metadata: An object describing how to interpret the given dataframes
            weight: The relative significance of the metric
        """
        super().__init__(
            table_metadata=table_metadata,
            weight=weight,
            lower_bound=0.0,
            upper_bound=1,
            ideal_value=0,
            greater_is_better=False
        )

    def _operate_on_frame(self, data: polars.DataFrame) -> polars.DataFrame:
        identifier = self.get_identifier()

        data = data.group_by(self.table_metadata.group_keys).agg(
            (
                polars.cov(ERROR_COLUMN, polars.int_range(0, polars.len())) / ERROR_COLUMN.var()
            ).alias(identifier),
            SAMPLE_SIZE,
        )
        return data


def normalize_time(table_metadata: PairTableMetadata, data: polars.DataFrame) -> polars.DataFrame:
    """
    Convert the data's datetime column to an integer value for use in calculations

    Args:
        table_metadata: Metadata about what columns do what in the data
        data: The data to transform

    Returns:
        The same data but with the datetime column in integers that reflect the unit for the values
    """
    if table_metadata.time_column_name not in data.columns:
        raise polars.exceptions.SchemaError(f"There is no '{table_metadata.time_column_name}' column in the input data")

    if not isinstance(data[table_metadata.time_column_name].dtype, polars.Datetime):
        raise polars.exceptions.SchemaError(
            f"The '{table_metadata.time_column_name}' column is a '{data[table_metadata.time_column_name].dtype}' "
            f"column, not a '{polars.Datetime}' column"
        )

    # If there's a time unit on the unit of measurement, that is what the time should be represented in. If the
    # measurement is in seconds, such as cubic feet per second, converting the time to integers blindly may yield
    # nanoseconds which might skew results by several orders of magnitude
    time_unit: typing.Optional[str] = units.time_unit(table_metadata.unit_name)

    if time_unit and time_unit.lower() in ('second', 'seconds', 's'):
        expression = table_metadata.time_column.dt.cast_time_unit("ms").cast(polars.Int64) / 1000.0
    elif time_unit and time_unit.lower() in ('minute', 'minutes', 'm'):
        expression = table_metadata.time_column.dt.cast_time_unit("ms").cast(polars.Int64) / (60 * 1000.0)
    elif time_unit and time_unit.lower() in ("hour", "hours", "h"):
        expression = table_metadata.time_column.dt.cast_time_unit("ms").cast(polars.Int64) / (60 * 60 * 1000.0)
    elif time_unit and time_unit.lower() in ("day", "days", "d"):
        expression = table_metadata.time_column.dt.cast_time_unit("ms").cast(polars.Int64) / (24 * 60 * 60 * 1000.0)
    elif time_unit and time_unit.lower() in ('millisecond', 'milliseconds', 'ms'):
        expression = table_metadata.time_column.dt.cast_time_unit("ms").cast(polars.Int64)
    elif time_unit and time_unit.lower() in ("nanosecond", "nanoseconds", "ns"):
        expression = table_metadata.time_column.dt.cast_time_unit("ns").cast(polars.Int64)
    elif time_unit and time_unit.lower() in ("microsecond", "microsecodns", "μs", "us"):
        expression = table_metadata.time_column.dt.cast_time_unit("us").cast(polars.Int64)

    else:
        expression = table_metadata.time_column.cast(polars.Int64)

    return data.with_columns(expression.alias(table_metadata.time_column_name))


def filter_pairs(
    table_metadata: PairTableMetadata,
    data: polars.DataFrame,
    threshold_column_name: str,
    control_comparison: typing.Callable[[polars.Expr, polars.Expr], polars.Expr] = operator.gt,
    simulation_comparison: typing.Callable[[polars.Expr, polars.Expr], polars.Expr] = None
) -> polars.DataFrame:
    """
    Constrain the given data in relation to the values within a column marked as a threshold

    For an input dataframe like:

    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | datetime            | control_location | control | simulation_location | simulation | threshold_0 | threshold_1 |
    +=====================+==================+=========+=====================+============+=============+=============+
    | 1970-01-01 00:00:00 | location 0       | 5.14    | Site 0              | 4.55       | 4           | 7           |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | 1970-01-01 01:00:00 | location 0       | 3.78    | Site 0              | 4.24       | 4           | 7           |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | ...                 | ...              | ...     | ...                 | ...        | ...         | ...         |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | 1975-12-31 23:59:00 | location N       | 4586    | Site N              | 4555       | 3000        | 8000        |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+

    length = 5,196,000

    Calling `filter(frame, 'threshold_0')` might yield:

    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | datetime            | control_location | control | simulation_location | simulation | threshold_0 | threshold_1 |
    +=====================+==================+=========+=====================+============+=============+=============+
    | 1970-01-01 00:00:00 | location 0       | 5.14    | Site 0              | 4.55       | 4           | 7           |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | ...                 | ...              | ...     | ...                 | ...        | ...         | ...         |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | 1975-12-31 23:00:00 | location N       | 4586    | Site N              | 4555       | 3000        | 8000        |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+

    length = 44,844

    While calling `filter(frame, 'threshold_1')` might yield:

    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | datetime            | control_location | control | simulation_location | simulation | threshold_0 | threshold_1 |
    +=====================+==================+=========+=====================+============+=============+=============+
    | 1970-05-01 14:00:00 | location 0       | 10.14   | Site 0              | 9.55       | 8           | 10          |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | 1970-02-03 07:00:00 | location 14      | 9.78    | Site 14             | 8.24       | 3           | 8           |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | ...                 | ...              | ...     | ...                 | ...        | ...         | ...         |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | 1975-11-14 23:00:00 | location 92      | 14586   | Site 92             | 12833      | 3000        | 8000        |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+

    length = 872

    Args:
        table_metadata: Metadata about what columns mean what
        data: The dataframe to filter
        threshold_column_name: The name of the threshold to use as the basis for filtering
        control_comparison: How to compare the control against the threshold (if at all)
        simulation_comparison: How to compare the simulation against the threshold (if at all)

    Returns:
        A new dataframe containing only values whose control and/or simulation values meet the comparison criteria
            when compared against the named threshold
    """
    if control_comparison is None or simulation_comparison is None:
        return data

    threshold_column: polars.Expr = polars.col(threshold_column_name)

    control_expression: polars.Expr = control_comparison(table_metadata.control_column, threshold_column)
    simulation_expression: polars.Expr = simulation_comparison(table_metadata.simulation_column, threshold_column)

    if None not in (control_comparison, simulation_comparison):
        data = data.filter(control_expression.and_(simulation_expression))
    elif simulation_comparison is not None:
        data = data.filter(simulation_comparison)
    else:
        data = data.filter(control_expression)

    return data


def mark_exceedence(
    table_metadata: PairTableMetadata,
    data: polars.DataFrame,
    threshold_column_name: str
) -> polars.DataFrame:
    """
    Create a copy of the given dataframe with new columns stating whether the control and simulation
    values exceed the threshold

    For an input dataframe like:

    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | datetime            | control_location | control | simulation_location | simulation | threshold_0 | threshold_1 |
    +=====================+==================+=========+=====================+============+=============+=============+
    | 1970-01-01 00:00:00 | location 0       | 3.14    | Site 0              | 4.55       | 4           | 7           |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | 1970-01-01 01:00:00 | location 0       | 3.78    | Site 0              | 4.24       | 4           | 7           |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | ...                 | ...              | ...     | ...                 | ...        | ...         | ...         |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+
    | 1975-12-31 23:00:00 | location N       | 4586    | Site N              | 4555       | 3000        | 8000        |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+

    Expect an output dataframe that looks like:

    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
    | datetime            | control_location | control | simulation_location | simulation | threshold_0 | threshold_1 | control_exceeds | simulation_exceeds |
    +=====================+==================+=========+=====================+============+=============+=============+=================+====================+
    | 1970-01-01 00:00:00 | location 0       | 3.14    | Site 0              | 4.55       | 4           | 7           | False           | True               |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
    | 1970-01-01 01:00:00 | location 0       | 3.78    | Site 0              | 4.24       | 4           | 7           | False           | True               |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
    | ...                 | ...              | ...     | ...                 | ...        | ...         | ...         | ...             | ...                |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
    | 1975-12-31 23:00:00 | location N       | 4586    | Site N              | 4555       | 3000        | 8000        | True            | True               |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+

    Args:
        table_metadata: The metadata explaining what columns do what in the dataframe
        data: The DataFrame containing the data to mark
        threshold_column_name: The name of the column containing the threshold that will serve as the basis for comparison

    Returns:
        A copy of the given DataFrame with new columns stating whether the control and simulation exceed the threshold
    """
    threshold_column: polars.Expr = polars.col(threshold_column_name)

    # Add columns for where simulation values and control values exceed the given threshold
    data = data.with_columns(**{
        SIMULATION_EXCEEDS_LABEL: table_metadata.simulation_column > threshold_column,
        CONTROL_EXCEEDS_LABEL: table_metadata.control_column > threshold_column,
    })
    return data


def create_contingency_table(
    table_metadata: PairTableMetadata,
    data: polars.DataFrame,
    control_exceedence_label: str = CONTROL_EXCEEDS_LABEL,
    simulation_exceedance_label: str = SIMULATION_EXCEEDS_LABEL
) -> polars.DataFrame:
    """
    Create a new DataFrame forming a contingency table based around the given threshold column

    The input DataFrame must have the following columns:
        - A boolean column stating whether the control values exceed the threshold
        - A boolean column stating whether the simulation values exceed the threshold

    For an input dataframe like:

    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
    | datetime            | control_location | control | simulation_location | simulation | threshold_0 | threshold_1 | control_exceeds | simulation_exceeds |
    +=====================+==================+=========+=====================+============+=============+=============+=================+====================+
    | 1970-01-01 00:00:00 | location 0       | 3.14    | Site 0              | 4.55       | 4           | 7           | False           | True               |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
    | 1970-01-01 01:00:00 | location 0       | 3.78    | Site 0              | 4.24       | 4           | 7           | False           | True               |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
    | ...                 | ...              | ...     | ...                 | ...        | ...         | ...         | ...             | ...                |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+
    | 1975-12-31 23:00:00 | location N       | 4586    | Site N              | 4555       | 3000        | 8000        | True            | True               |
    +---------------------+------------------+---------+---------------------+------------+-------------+-------------+-----------------+--------------------+

    Expect an output dataframe that looks like:

    +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+
    | control_location | simulation_location | hit | miss | false_positive | true_negative | positive_controls | negative_controls | positive_simulation | negative_simulation | sample_size |
    +==================+=====================+=====+======+================+===============+===================+===================+=====================+=====================+=============+
    | location 0       | Site 0              | 15  | 455  | 17             | 888           | 470               | 905               | 32                  | 1343                | 1375        |
    +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+
    | location 1       | Site 1              | 17  | 322  | 84             | 972           | 339               | 1056              | 101                 | 1294                | 1395        |
    +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+
    | location 1       | Site 1a             | 32  | 105  | 12             | 1300          | 137               | 1312              | 44                  | 1305                | 1349        |
    +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+
    | ...              | ...                 | ... | ...  | ...            | ...           | ...               | ...               | ...                 | ...                 | ...         |
    +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+
    | location N       | Site N              | 72  | 18   | 1576           | 200           | 90                | 1776              | 1648                | 218                 | 1866        |
    +------------------+---------------------+-----+------+----------------+---------------+-------------------+-------------------+---------------------+---------------------+-------------+

    Args:
        table_metadata: Metadata about the table describing what column does what
        data: The DataFrame to create the contingency table for
        control_exceedence_label: The label of the boolean column stating if the control value exceeded the threshold
        simulation_exceedance_label: The label of the boolean column stating if the simulation value exceeded the threshold

    Returns:
        A new dataframe describing the hits, misses, false positives, and true negatives for all matching
        locations for the given numerical column
    """
    # Make sure that the given columns may be used
    if control_exceedence_label not in data.columns and simulation_exceedance_label not in data.columns:
        raise polars.exceptions.SchemaError(
            f"the data for create_contingency_table must have the boolean columns "
            f"with the given names: '{control_exceedence_label}' and '{simulation_exceedance_label}', but both "
            f"are missing. Call mark_exceedence or form them manually before "
            f"calling this. Available columns are: {data.columns}"
        )

    if control_exceedence_label not in data.columns:
        raise polars.exceptions.SchemaError(
            f"the data for create_contingency_table must have a boolean column "
            f"with the given name '{control_exceedence_label}', but it is missing. Call "
            f"mark_exceedence or form them manually before calling this. "
            f"Available columns are: {data.columns}"
        )

    if simulation_exceedance_label not in data.columns:
        raise polars.exceptions.SchemaError(
            f"the data for create_contingency_table must have a boolean column "
            f"with the given name '{simulation_exceedance_label}', but it is missing. Call "
            f"mark_exceedence or form them manually before calling this. "
            f"Available columns are: {data.columns}"
        )

    if any(data[label].dtype != polars.Boolean for label in [control_exceedence_label, simulation_exceedance_label]):
        raise polars.exceptions.SchemaError(
            f"The data for create_contingency_table is not valid. The "
            f"'{control_exceedence_label}' and '{simulation_exceedance_label}' columns must be boolean values "
            f"but were {data[control_exceedence_label].dtype} and {data[simulation_exceedance_label].dtype} instead"
        )

    control_exceeds: polars.Expr = polars.col(control_exceedence_label)
    simulation_exceeds: polars.Expr = polars.col(simulation_exceedance_label)

    # Create boolean values describing if we've encountered a hit, a miss, a false positive, or a true negative.
    #   These will be used for aggregation
    data = data.with_columns(**{
        HITS_LABEL: simulation_exceeds & control_exceeds,
        MISSES_LABEL: control_exceeds & ~simulation_exceeds,
        FALSE_POSITIVE_LABEL: simulation_exceeds & ~control_exceeds,
        TRUE_NEGATIVE_LABEL: ~simulation_exceeds & ~control_exceeds,
    })

    # group upon the given columns and count the number of true hits, misses, false positives, and true negatives
    data = data.group_by(table_metadata.group_keys).agg(
        HITS_COLUMN.sum(),
        MISSES_COLUMN.sum(),
        FALSE_POSITIVE_COLUMN.sum(),
        TRUE_NEGATIVE_COLUMN.sum(),
        table_metadata.control_column.count().alias(SAMPLE_SIZE_LABEL)
    )

    # Add counts for how often the control and simulated values did or didn't fit the thresholds
    data = data.with_columns(
        POSITIVE_CONTROLS,
        NEGATIVE_CONTROLS,
        POSITIVE_SIMULATIONS,
        NEGATIVE_SIMULATIONS,
    )
    return data


def is_contingency_table(data: polars.DataFrame) -> bool:
    """
    Indicates whether a table is a contingency table

    Args:
        data: The dataframe to check

    Returns:
        True if the data is a contingency table, False otherwise
    """
    errors: typing.Optional[str] = validate_partial_schema(
        data=data,
        required_schema={
            HITS_LABEL: polars.datatypes.classes.NumericType,
            MISSES_LABEL: polars.datatypes.classes.NumericType,
            FALSE_POSITIVE_LABEL: polars.datatypes.classes.NumericType,
            TRUE_NEGATIVE_LABEL: polars.datatypes.classes.NumericType,
            SAMPLE_SIZE_LABEL: polars.datatypes.classes.NumericType,
            POSITIVE_SIMULATIONS_LABEL: polars.datatypes.classes.NumericType,
            POSITIVE_CONTROLS_LABEL: polars.datatypes.classes.NumericType,
            NEGATIVE_SIMULATIONS_LABEL: polars.datatypes.classes.NumericType,
            NEGATIVE_CONTROLS_LABEL: polars.datatypes.classes.NumericType,
        },
        throw=False
    )
    return errors is None


def can_become_contingency_table(data: polars.DataFrame, metadata: PairTableMetadata, threshold_name: str) -> bool:
    """
    Determines if the data is not a contingency table but may become one

    Args:
        data: The dataframe to check
        metadata: Data about what the columns in the data mean
        threshold_name: The name of the threshold that the contingency table will be based upon

    Returns:
        True if a dataframe may become a data frame but is not one
    """
    if is_contingency_table(data):
        return False

    required_fields: typing.Collection[str] = (
        metadata.control_column_name,
        metadata.simulation_column_name,
        threshold_name,
        *metadata.group_keys
    )
    return all(field in data.columns for field in required_fields)


def validate_partial_schema(
    data: polars.DataFrame,
    required_schema: typing.Mapping[str, polars.datatypes.DataTypeClass],
    throw: bool = True
) -> typing.Optional[str]:
    """
    Verify if the schema of the given data is a superset of the given partial schema

    The data may have more columns than the partial schema and the types of the data's columns may be
    subtypes (such as `uint8` instead of `IntegerType`), but an exception will be thrown if a data type isn't a
    subtype or a column is not present

    Args:
        data: The data to validate
        required_schema: The bare minimum columns and their types that are required
        throw: Throw an exception if the validation fails

    Returns:
        A record of any possible error
    """
    wrong_types: typing.List[typing.Tuple[str, polars.DataType, polars.datatypes.DataTypeClass]] = []
    """
    A record of all columns that are of the wrong type. [0] is the name of the column, [1] is the encountered type, 
    [2] is the expected type
    """

    missing_columns: typing.List[str] = []
    """A record of all columns that are required but not in the data"""

    for column_name, required_type in required_schema.items():
        if column_name not in data.columns:
            missing_columns.append(column_name)
        elif not isinstance(data[column_name].dtype, required_type):
            wrong_types.append((column_name, data[column_name].dtype, required_type))

    message = ""

    if wrong_types:
        message += "The following columns have the wrong type:" + os.linesep

        for column_name, encountered_type, expected_type in wrong_types:
            message += f"    - {column_name} was {encountered_type} but was supposed to be {expected_type}"
            message += os.linesep

    if missing_columns:
        message += "The following columns were missing:" + os.linesep

        for missing_column in missing_columns:
            message += f"    - {missing_column}"
            message += os.linesep

    if message and throw:
        raise polars.exceptions.SchemaError(f"Invalid schema encountered: {message}")

    return message if len(message.strip()) > 0 else None