"""
Unit tests intended to prove the correctness of expression evaluation
"""
import functools
import typing
import unittest
import random

from datetime import datetime
from datetime import timedelta

import numpy
import polars

from ...metrics import expressions
from ...metrics import scoring

CONTROL_COLUMN_NAME: typing.Final[str] = "control"
"""The name of the column containing control values"""

SIMULATION_COLUMN_NAME: typing.Final[str] = "simulation"
"""The name of the column containing simulation values"""

CONTROL_LOCATION_COLUMN_NAME: typing.Final[str] = "control_location"
"""The name of the column that contains the names of locations of control data"""

CONTROL_LOCATION_PREFIX: typing.Final[str] = "Location "
"""The format for the name of a location of control data"""

SIMULATION_LOCATION_COLUMN_NAME: typing.Final[str] = "simulation_location"
"""The name of the column that contains the names of locations of simulation data"""

SIMULATION_LOCATION_PREFIX: typing.Final[str] = "Site "

TIME_COLUMN_NAME: typing.Final[str] = "datetime"
"""The name of the column that contains the times that values occurred"""

CONFIDENCE: typing.Final[float] = 0.95
"""The percentage to use for the confidence interval"""

CONFIDENCE_INTERVAL_ITERATIONS: typing.Final[int] = 200
"""The number of times to resample to recalculate the confidence interval"""

UNIT_NAME: typing.Final[str] = "cms"
"""The name of the measurement unit in use"""

THRESHOLD_PERCENTILES: typing.Final[typing.Sequence[float]] = [0.5, 0.75, 0.95]
"""The thresholds to evaluate"""

THRESHOLD_NAME_FORMAT: typing.Final[str] = "Threshold_{}"
"""The format used to generate threshold names"""

LOCATION_COUNT: typing.Final[int] = 300
"""The number of locations to evaluate"""

START_DATE: typing.Final[datetime] = datetime(year=2023, month=1, day=1)
"""When to start the period of data"""

END_DATE: typing.Final[datetime] = datetime(year=2023, month=6, day=30)
"""When to end the period of data"""

TIME_INTERVAL: typing.Final[timedelta] = timedelta(hours=1)
"""The amount of time between values"""

VALUE_RANGE: typing.Final[float] = 30.0
"""The range in which values for a location may differ"""

VALUE_BOUNDS: typing.Final[typing.Tuple[float, float]] = (15.0, 200.0)
"""The range in which values for a location may be generated"""

TEST_SCHEMA: typing.Mapping[str, typing.Union[polars.datatypes.classes.DataTypeClass, str]] = {
    CONTROL_COLUMN_NAME: polars.Float64,
    SIMULATION_COLUMN_NAME: polars.Float64,
    TIME_COLUMN_NAME: polars.Datetime,
    SIMULATION_LOCATION_COLUMN_NAME: polars.String,
    CONTROL_LOCATION_COLUMN_NAME: polars.String,
    **{THRESHOLD_NAME_FORMAT.format(index): polars.Float64 for index in range(len(THRESHOLD_PERCENTILES))}
}
"""The schema for what the test data should look like"""


def generate_test_dataframe(seed: int = None) -> polars.DataFrame:
    """
    Generate dataframe of test data

    Args:
        seed: The seed value used to ensure that random values are consistent

    Returns:
        Random values used for expression testing
    """
    if seed is None:
        seed = 54468464

    randomizer = numpy.random.default_rng(seed)
    test_data: polars.DataFrame = polars.DataFrame()

    for location_pairing in range(LOCATION_COUNT):
        frame = polars.DataFrame()

        lower_bound: float = randomizer.uniform(*VALUE_BOUNDS)
        upper_bound: float = lower_bound + VALUE_RANGE

        range_of_values: typing.Sequence[float] = numpy.arange(
            lower_bound,
            upper_bound,
            (upper_bound - lower_bound) / VALUE_RANGE
        )

        frame = frame.with_columns(
            polars.datetime_range(START_DATE, END_DATE, TIME_INTERVAL).alias(TIME_COLUMN_NAME),
        )
        frame = frame.with_columns(
            polars.repeat(location_pairing, polars.len()).cast(polars.String).alias("index"),
            polars.repeat(SIMULATION_LOCATION_PREFIX, polars.len()).alias("simulation_location_prefix"),
            polars.repeat(CONTROL_LOCATION_PREFIX, polars.len()).alias("control_location_prefix"),
        )
        frame = frame.with_columns(
            polars.col("index").map_elements(
                lambda _: randomizer.uniform(lower_bound, upper_bound),
                return_dtype=polars.Float64
            ).alias(SIMULATION_COLUMN_NAME),
            (polars.col("simulation_location_prefix") + polars.col("index")).alias(SIMULATION_LOCATION_COLUMN_NAME),
            (polars.col("control_location_prefix") + polars.col("index")).alias(CONTROL_LOCATION_COLUMN_NAME),
        ).with_columns(
            polars.col(SIMULATION_COLUMN_NAME).map_elements(
                lambda value: value + randomizer.uniform(-value * 0.1, value * 0.1),
                return_dtype=polars.Float64
            ).alias(CONTROL_COLUMN_NAME),
        )
        frame = frame.with_columns(**{
            THRESHOLD_NAME_FORMAT.format(threshold_index): polars.repeat(
                numpy.percentile(range_of_values, percentile),
                n=polars.len()
            )
            for threshold_index, percentile in enumerate(THRESHOLD_PERCENTILES)
        }).drop("simulation_location_prefix", "control_location_prefix", "index")

        test_data = polars.concat([test_data, frame])

    return test_data


class ExpressionTest(unittest.TestCase):
    """
    Test `dmod.metrics.expressions`
    """
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dataframe: polars.DataFrame = generate_test_dataframe()
        cls.location_names: typing.Sequence[typing.Dict[str, str]] = cls.test_dataframe.unique(
            [CONTROL_LOCATION_COLUMN_NAME, SIMULATION_LOCATION_COLUMN_NAME]
        ).select([CONTROL_LOCATION_COLUMN_NAME, SIMULATION_LOCATION_COLUMN_NAME]).rows(named=True)

        cls.threshold_columns: typing.Sequence[str] = [
            column_name
            for column_name in cls.test_dataframe.columns
            if column_name.startswith(THRESHOLD_NAME_FORMAT[:-3])
        ]

        cls.table_metadata: expressions.PairTableMetadata = expressions.PairTableMetadata(
            control_column_name=CONTROL_COLUMN_NAME,
            control_location_column_name=CONTROL_LOCATION_COLUMN_NAME,
            simulation_column_name=SIMULATION_COLUMN_NAME,
            simulation_location_column_name=SIMULATION_LOCATION_COLUMN_NAME,
            time_column_name=TIME_COLUMN_NAME,
            unit_name=UNIT_NAME,
            confidence_interval=CONFIDENCE,
            confidence_interval_iterations=CONFIDENCE_INTERVAL_ITERATIONS
        )
        cls.general_metric_weight: float = 1.0
        cls.general_threshold_weight: float = 1.0

    def perform_metric_test(self, metric: expressions.MetricExpression):
        for threshold_name in self.threshold_columns:
            threshold: scoring.ThresholdMetadata = scoring.ThresholdMetadata(
                name=threshold_name,
                weight=self.general_threshold_weight
            )

            scores: typing.Sequence[scoring.Score] = metric.evaluate(self.test_dataframe, threshold=threshold)

            required_locations = list(self.location_names)

            for score in scores:
                required_location: typing.Dict[str, str] = {
                    CONTROL_LOCATION_COLUMN_NAME: score.control_location,
                    SIMULATION_LOCATION_COLUMN_NAME: score.simulation_location
                }

                required_locations.remove(required_location)
                self.assertTrue(isinstance(score.value, (int, float)))

                if score.sample_size == 0:
                    self.assertTrue(numpy.isnan(score.value))
                else:
                    self.assertFalse(numpy.isnan(score.value))

                if numpy.isnan(score.value):
                    self.assertTrue(numpy.isnan(score.scaled_value))
                else:
                    self.assertFalse(numpy.isnan(score.scaled_value))

                if numpy.isnan(score.scaled_value):
                    self.assertTrue(numpy.isnan(score.value))
                else:
                    self.assertFalse(numpy.isnan(score.value))

            if required_locations:
                missing_locations: typing.Sequence[str] = [
                    f"[{control_location}, {simulated_location}]"
                    for control_location, simulated_location in required_locations
                ]
                message = f"The following results are missing: {', '.join(missing_locations)}"
                self.assertTrue(len(required_locations) == 0, message)

    def test_probability_of_detection(self):
        metric = expressions.ProbabilityOfDetection(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_false_alarm_ratio(self):
        metric = expressions.FalseAlarmRatio(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_probability_of_false_detection(self):
        metric = expressions.ProbabilityOfFalseDetection(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_frequency_bias(self):
        metric = expressions.FrequencyBias(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_accuracy(self):
        metric = expressions.Accuracy(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_critical_success_index(self):
        metric = expressions.CriticalSuccessIndex(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_equitable_threat_score(self):
        metric = expressions.EquitableThreatScore(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_general_skill(self):
        metric = expressions.GeneralSkill(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_precision(self):
        metric = expressions.Precision(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_pearson_correlation_coefficient(self):
        metric = expressions.PearsonCorrelationCoefficient(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_kling_gupta_efficiency(self):
        metric = expressions.KlingGuptaEfficiency(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_volume_error(self):
        metric = expressions.VolumeError(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_normalized_nash_sutcliffe_efficiency(self):
        metric = expressions.NormalizedNashSutcliffeEfficiency(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)

    def test_linear_temporal_trend_absolute_error(self):
        metric = expressions.LinearTemporalTrendAbsoluteError(
            table_metadata=self.table_metadata,
            weight=self.general_metric_weight
        )

        self.perform_metric_test(metric)


if __name__ == '__main__':
    unittest.main()
