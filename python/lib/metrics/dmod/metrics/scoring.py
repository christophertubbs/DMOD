"""
Defines classes and functions used to combine and score data for metrics
"""
from __future__ import annotations

import json
import typing
import string
import abc
import re
import itertools

from collections import UserDict
from collections import defaultdict
from collections import abc as abstract_collections

from math import inf as infinity

import polars
import numpy

from dmod.core import common
from .expressions import MetricExpression

from .threshold import Threshold
from .threshold import ThresholdMetadata
from .communication import Verbosity
from .communication import CommunicatorGroup

ARGS = typing.Optional[typing.Sequence]
KWARGS = typing.Optional[typing.Dict[str, typing.Any]]
NUMBER = typing.Union[int, float]

METRIC = typing.Callable[[polars.DataFrame, polars.DataFrame, typing.Sequence[ThresholdMetadata], ARGS, KWARGS], NUMBER]
NUMERIC_OPERATOR = typing.Callable[[NUMBER, NUMBER, typing.Optional[NUMBER]], NUMBER]
NUMERIC_TRANSFORMER = typing.Callable[[NUMBER], NUMBER]
NUMERIC_FILTER = typing.Callable[[NUMBER, NUMBER], bool]
FRAME_FILTER = typing.Callable[[polars.DataFrame], polars.DataFrame]


EPSILON = 0.0001

WHITESPACE_PATTERN = re.compile(f"[{string.whitespace}]+")


def scale_value(metric: MetricType, raw_value: NUMBER) -> NUMBER:
    """
    Rescales the result of a metric to bear a value in relation to the metric's ideal value.

    If a metric has an ideal value of 1 with the bounds of 0 and 1 and a raw value of 0.75, the scaled value is 0.75
    If a metric has an ideal value of 0 with the bounds of 0 and 1 and a raw value of 0.75, the scaled value is 0.25
    If a metric has an ideal value of 0 with the bounds of -1 and 1 and a raw value of 0.75, the scaled value is 0.25
    If a metric has an ideal value of 0 with the bounds of -1 and 1 and a raw value of 0.25, the scaled value is 0.75
    If a metric has an ideal value of 0 with the bounds of -1 and 1 and a raw value of -0.25, the scaled value is 0.75
    If a metric has an ideal value of 0 with the bounds of -1 and 1 and a raw value of 0.25, the scaled value is 0.75

    Args:
        metric: The metric that was run
        raw_value: The result of the metric that was run

    Returns:
        The raw value scaled between the metric's bounds in relation to the metric's ideal value
    """
    if numpy.isnan(raw_value):
        return numpy.nan

    if not metric.has_ideal_value or not metric.bounded:
        return raw_value

    rise = 0
    run = 1

    if metric.ideal_value == metric.lower_bound:
        # Lower should be higher and the max scale factor is 1.0 and the minimum is 0.0
        rise = -1
        run = metric.upper_bound - metric.lower_bound
    elif metric.ideal_value == metric.upper_bound:
        # lower should stay lower, meaning that the scale should move from 0 to 1
        rise = 1
        run = metric.upper_bound - metric.lower_bound
    elif metric.lower_bound < metric.ideal_value < metric.upper_bound and raw_value <= metric.ideal_value:
        # If the ideal is between the bounds and the raw value is less than the ideal, the value will be scaled
        # in an upwards direction
        rise = 1
        run = metric.ideal_value - metric.lower_bound
    elif metric.lower_bound < metric.ideal_value < metric.upper_bound and raw_value > metric.ideal_value:
        # If the ideal is between the bounds and the raw value is greater than the ideal, the value will be scaled
        # in a downwards direction
        rise = -1
        run = metric.upper_bound - metric.ideal_value

    # This will set up a very basic slope-intercept form of a line (y = slope * x + value of y at x=0).
    # The metric value will be scaled linearly along the constructed line
    slope = rise / run
    y_intercept = 1 - (slope * metric.ideal_value)

    # The scaled value will be the y value of the constructed line with the raw value serving as the input x value
    scaled_value = slope * raw_value + y_intercept

    # Ensure that value is scaled to the maximum at most
    if metric.has_upper_bound:
        scaled_value = min(scaled_value, metric.upper_bound)

    # Ensure that the value is scaled to the minimum at least
    if metric.has_lower_bound:
        scaled_value = max(scaled_value, metric.lower_bound)

    return scaled_value


def keys_are_uniform(
    first_keys: typing.Iterable[typing.Union[ResultKey, ResultKey.Owns]],
    second_keys: typing.Iterable[typing.Union[ResultKey, ResultKey.Owns]]
) -> bool:
    """
    Checks to see if the keys in the first set all match the keys in the second set

    Args:
        first_keys: A collection of keys or items that have a key within a `key` parameter
        second_keys: A collection of keys or items that have a key within a `key` parameter

    Returns:
        True if they all have the same key value, False otherwise
    """
    def get_key(key: typing.Union[ResultKey, ResultKey.Owns]) -> ResultKey:
        return key.key if isinstance(key, ResultKey.Owns) else key

    return all(
        get_key(key=key_one) == get_key(key=key_two)
        for key_one, key_two in itertools.product(first_keys, second_keys)
    )


def create_identifier(name: str) -> str:
    """
    Returns an identifier that may be compared against other strings for identification

    This will convert "Pearson Correlation Coefficient" to "pearsoncorrelationcoefficient"

    If a function tries to find a metric by name, it can compare and find the metric with values like
    "pEArSoNcOrreLaTionC oeffIcIEnT" or "pearson correlation_coefficient"

    Returns:
        An identifier that may be compared against other strings for identification
    """
    identifier = WHITESPACE_PATTERN.sub("", name)
    identifier = identifier.replace("_", "")

    identifier = identifier.strip()

    # chr(45) and chr(8211) are both different types of hyphens
    # chr(45) => '-'
    identifier = identifier.replace(chr(45), "")
    # chr(8211) => '–'
    identifier = identifier.replace(chr(8211), "")

    identifier = identifier.lower()
    return identifier


class MetricType(typing.Protocol):
    @classmethod
    def get_description(cls):
        """
        Returns:
            A description of how the metric works and how it's supposed be be interpreted
        """

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

    @property
    def name(self) -> str:
        """
        Returns:
            The name of the metric
        """

    @property
    def fails_on(self) -> NUMBER:
        """
        Returns:
            The value that might trigger a failing evaluation
        """

    @property
    def weight(self) -> NUMBER:
        """
        Returns:
            The relative numeric significance of the metric
        """

    @property
    def ideal_value(self) -> NUMBER:
        """
        Returns:
            The perfect value
        """

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

    @property
    def greater_is_better(self) -> bool:
        """
        Returns:
            Whether a greater value is considered better
        """

    @property
    def has_upper_bound(self) -> bool:
        ...

    @property
    def has_lower_bound(self) -> bool:
        ...

    @property
    def has_ideal_value(self) -> bool:
        ...

    @property
    def fully_bounded(self) -> bool:
        ...

    @property
    def partially_bounded(self) -> bool:
        ...

    @property
    def bounded(self) -> bool:
        ...

    @classmethod
    def get_name(cls) -> str:
        pass


class Metric(
    abc.ABC,
    typing.Callable[[polars.DataFrame, str, str, typing.Optional[typing.Sequence[ThresholdMetadata]], ARGS, KWARGS], "Scores"]
):
    """
    A functional that may be called to evaluate metrics based around thresholds, providing access to attributes
    such as its name and bounds
    """
    def __init__(
        self,
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
            weight: The relative, numeric significance of the metric itself
            lower_bound: The lowest acknowledged value - this doesn't necessarily need to be the lower bound of the statistical function
            upper_bound: The highest acknowledged value - this doesn't necessarily need to be the upper bound of the statistical function
            ideal_value: The value deemed to be perfect for the metric
            failure: A value indicating a complete failure for the metric, triggering a failure among all accompanying metrics
            greater_is_better: Whether a higher value is preferred over a lower value
        """
        if weight is None or not isinstance(weight, (int, float)) or numpy.isnan(weight):
            raise ValueError("Weight must be supplied and must be numeric")

        self.__lower_bound = lower_bound if lower_bound is not None else -infinity
        self.__upper_bound = upper_bound if upper_bound is not None else infinity
        self.__ideal_value = ideal_value if ideal_value is not None else numpy.nan
        self.__weight = weight
        self.__greater_is_better = greater_is_better if greater_is_better is not None else True
        self.__failure = failure

    @classmethod
    @abc.abstractmethod
    def get_description(cls):
        """
        Returns:
            A description of how the metric works and how it's supposed be be interpreted
        """

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
        return not numpy.isnan(self.__upper_bound) and self.__upper_bound < infinity

    @property
    def has_lower_bound(self) -> bool:
        return not numpy.isnan(self.__lower_bound) and self.__lower_bound > -infinity

    @property
    def has_ideal_value(self) -> bool:
        return self.__ideal_value is not None and \
               not numpy.isnan(self.__ideal_value) and \
               not numpy.isinf(self.__ideal_value)

    @property
    def fully_bounded(self) -> bool:
        return self.has_lower_bound and self.has_upper_bound

    @property
    def partially_bounded(self) -> bool:
        return self.has_lower_bound ^ self.has_upper_bound

    @property
    def bounded(self) -> bool:
        return self.has_lower_bound or self.has_upper_bound

    @classmethod
    @abc.abstractmethod
    def get_name(cls) -> str:
        pass

    @abc.abstractmethod
    def __call__(
        self,
        pairs: polars.DataFrame,
        observed_value_label: str,
        predicted_value_label: str,
        thresholds: typing.Sequence[Threshold] = None,
        communicators: CommunicatorGroup = None,
        *args,
        **kwargs
    ) -> Scores:
        pass

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return "Metric(name=" + self.name + ")"


class ConfidenceInterval:
    """
    Represents the confidence interval of a metric
    """
    def __init__(self, confidence: float, lower_bound: float, upper_bound: float):
        # Assume the value is a percentage if it is greater than 1, otherwise it is a decimal, so convert that into
        #   a percentage
        self.__confidence = confidence if confidence >= 1.0 else confidence * 100.0
        self.__lower_bound = lower_bound
        self.__upper_bound = upper_bound

    @property
    def confidence(self) -> float:
        """
        The degree of confidence, in percentage, that the true value is between the upper and lower bound
        """
        return self.__confidence

    @property
    def lower_bound(self) -> float:
        """
        The minimum possible value
        """
        return self.__lower_bound

    @property
    def upper_bound(self) -> float:
        """
        The maximum possible value
        """
        return self.__upper_bound

    def to_dict(self) -> typing.Dict[str, float]:
        """
        Convert information about the interval to a dictionary
        """
        return {
            "confidence": self.confidence,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
        }

    def __str__(self) -> str:
        return f"{self.confidence:.3f}% sure the true value is between {self.lower_bound} and {self.upper_bound}"

    def __repr__(self):
        return f"{self.__confidence:.3f}%: [{self.lower_bound}, {self.upper_bound}]"


class Score(object):
    """
    Information about the resultant value of a metric
    """
    def __init__(
        self,
        metric: MetricType,
        value: NUMBER,
        threshold: ThresholdMetadata,
        key: ResultKey,
        sample_size: int = None,
        confidence_interval: ConfidenceInterval = None,
    ):
        self.__metric = metric
        self.__value = value
        self.__confidence_interval = confidence_interval
        self.__threshold = threshold
        self.__key = key
        self.__sample_size = sample_size or numpy.nan

    @property
    def key(self) -> ResultKey:
        """
        The key that differentiates this from any other result
        """
        return self.__key

    @property
    def value(self) -> NUMBER:
        """
        The result of the metric
        """
        return self.__value

    @property
    def confidence_interval(self) -> typing.Optional[ConfidenceInterval]:
        """
        The range of between we are x% certain the value is correct
        """
        return self.__confidence_interval

    @property
    def grade(self) -> NUMBER:
        """
        The normalized metric score on a scale from 0 to 100
        """
        return scale_value(self.__metric, self.__value) * 100.0

    @property
    def scaled_value(self) -> NUMBER:
        """
        The normalized metric score as a fraction of the threshold's weight
        """
        return scale_value(self.__metric, self.__value) * self.__threshold.weight

    @property
    def metric(self) -> MetricType:
        """
        The metric that was performed
        """
        return self.__metric

    @property
    def threshold(self) -> ThresholdMetadata:
        """
        Information about the threshold that was used
        """
        return self.__threshold

    @property
    def failed(self) -> bool:
        """
        Whether the metric results indicate a failure

        A metric score is deemed a failure if the metric has a failure score (such as 0 for probability of detection)
        that matches the result of the metric
        """
        if self.__metric.fails_on is None:
            return False
        if numpy.isnan(self.__metric.fails_on) and numpy.isnan(self.__value):
            return True
        if numpy.isnan(self.__metric.fails_on):
            return False

        difference = self.__value - self.__metric.fails_on
        difference = abs(difference)

        failed = difference < EPSILON

        return bool(failed)

    @property
    def sample_size(self):
        """
        The number of values used to compute the metric
        """
        return self.__sample_size

    def to_dict(self) -> dict:
        """
        Convert the score to a dictionary ready to be serialized
        """
        return {
            "value": common.truncate(self.value, 2),
            "scaled_value": common.truncate(self.scaled_value, 2),
            "sample_size": common.truncate(self.sample_size, 2),
            "failed": self.failed,
            "weight": self.threshold.weight,
            "threshold": self.threshold.name,
            "grade": self.grade,
            "confidence_interval": None if self.confidence_interval is None else self.confidence_interval.to_dict(),
            **self.key
        }

    def __len__(self):
        return self.__sample_size

    def __str__(self) -> str:
        return f"[{self.key}] {self.metric} => ({self.threshold}: {self.scaled_value})"

    def __repr__(self) -> str:
        return self.__str__()


class ScoreDescription:
    """
    A simple class used to help organize finalized score data
    """
    def __init__(self, scores: typing.Sequence[Score]):
        self.__total: int = 0
        self.__maximum_metric_value: int = 0
        self.__weight: typing.Optional[int] = None
        self.__thresholds: typing.Dict[str, dict] = {}
        self.__scaled_value: int = 0
        self.__metric_name = None
        self.__key: typing.Optional[ResultKey] = None

        common.on_each(self.add_score, scores)

        self.update_scaled_value()

    def add_score(self, score: Score):
        """
        Add a score value and update derived attributes such as the scaled value

        Args:
            score: The metric result to add
        """
        if self.__key is None:
            self.__key = score.key
        elif self.__key != score.key:
            raise KeyError("Key mismatch - the preexisting scores are not compatible with incoming values")

        if self.__weight is None:
            self.__weight = score.metric.weight
            self.__metric_name = score.metric.name

        self.__thresholds[score.threshold.name] = score.to_dict()

        if not numpy.isnan(score.scaled_value):
            self.__maximum_metric_value += score.threshold.weight
            self.__total += score.scaled_value

    def update_scaled_value(self):
        """
        Update the value of the metric in terms of the significance of its weight and its potential ideal value
        """
        if self.has_value:
            scale_factor = self.__total / self.__maximum_metric_value
            self.__scaled_value = scale_factor * self.__weight

    def to_dict(self) -> dict:
        """
        Convert into a dictionary for easier transmission

        Returns:
            All of this object's data in the form of a dictionary
        """
        return {
            "total": self.__total,
            "maximum_possible_value": self.__maximum_metric_value,
            "scaled_value": self.__scaled_value,
            "thresholds": self.__thresholds,
            "weight": self.__weight
        }

    @property
    def has_value(self) -> bool:
        """
        Whether the score being described has any sort of actual value
        """
        total_has_value = self.__total != 0 and not numpy.isnan(self.__total)
        has_maximum_value = self.__maximum_metric_value != 0 and not numpy.isnan(self.__maximum_metric_value)
        has_weight = self.__weight != 0 and not numpy.isnan(self.__weight)

        return has_weight and total_has_value and has_maximum_value

    @property
    def name(self) -> str:
        """The name of the metric for the scores"""
        return self.__metric_name

    @property
    def weight(self) -> int:
        """The significance of the metric"""
        return self.__weight

    @property
    def value(self) -> float:
        """The sum of all scaled values of the contained scores"""
        return self.__total

    @property
    def scaled_value(self) -> float:
        """The value of all values in relation to the metric's significance"""
        return self.__scaled_value

    @property
    def maximum_value(self) -> float:
        """The maximum possible value of the collected scores"""
        return self.__maximum_metric_value

    @property
    def thresholds(self) -> typing.Dict[str, dict]:
        """A breakdown of each contained threshold"""
        return self.__thresholds

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.name}: {self.value} out of {self.maximum_value}"


class Scores(abstract_collections.Sequence):
    def __len__(self) -> int:
        return len(self.__results)

    def __init__(self, metric: MetricType, scores: typing.Sequence[Score]):
        self.__metric = metric

        self.__results = {
            score.threshold: score
            for score in scores
        }

    @property
    def metric(self) -> MetricType:
        return self.__metric

    @property
    def total(self) -> NUMBER:
        """
        The total of all scaled scores contained. Only non-null and non-empty scores are considered,
        otherwise values will be skewed

            n
            Σ   self.__results.values()[i].scaled_value
          i = 0
        """
        if len(self.__results) == 0:
            raise ValueError("There are no scores to total")

        return sum(
            score.scaled_value
            for score in self
            if not numpy.isnan(score.sample_size)
               and score.sample_size > 0
               and not numpy.isnan(score.scaled_value)
        )

    @property
    def performance(self) -> float:
        """
        Demonstrates the performance of the metrics in relation to the total possible value in relation to the
        highest possible value of all thresholds

        A perfect metric result for a score yields the weight of its threshold, anything else is a fraction of it.
        The performance is the sum of all scores divided by their max possible value.

        Only non-null and non-empty scores are considered. Results with low sample sizes can skew results otherwise.

            n
            Σ   self[i].scaled_value
          i = 0
        -----------------------------------
            n
            Σ   self[i].threshold.weight
          i = 0

        """
        valid_scores: typing.List[Score] = [
            score
            for score in self
            if not numpy.isnan(score.sample_size)
               and score.sample_size > 0
        ]
        max_possible = sum(score.threshold.weight for score in valid_scores)
        return self.total / max_possible if max_possible else numpy.nan

    @property
    def scaled_value(self) -> float:
        """
        Scales the weight of this metric by the performance of all scores to be a fraction of the metric's weight

            n
            Σ   self[i].scaled_value
          i = 0
        -----------------------------------  * self.metric.weight
            n
            Σ   self[i].threshold.weight
          i = 0

        """
        return self.performance * self.metric.weight

    def to_dict(self) -> dict:
        score_representation = {
            "total": self.total,
            "scaled_value": common.truncate(self.scaled_value, 2),
            "grade": "{:.2f}%".format(self.performance * 100) if not numpy.isnan(self.performance) else None,
            "scores": dict()
        }

        for threshold, score in self.__results.items():  # type: Threshold, Score
            score_representation['scores'][str(threshold)] = {
                "value": common.truncate(score.value, 2),
                "scaled_value": common.truncate(score.scaled_value, 2),
                "sample_size": common.truncate(score.sample_size, 2),
                "failed": score.failed,
                "weight": score.threshold.weight,
                "grade": common.truncate(score.grade, 3),
            }

        return score_representation

    def __getitem__(self, key: typing.Union[str, Threshold]) -> Score:
        if isinstance(key, Threshold):
            key = key.name

        for threshold, score in self.__results.items():
            if threshold.name == key:
                return score

        raise ValueError(f"There is not a score for '{key}'")

    def __iter__(self):
        return iter(self.__results.values())

    def __str__(self) -> str:
        return ", ".join([str(score) for score in self.__results])

    def __repr__(self) -> str:
        return self.__str__()


class ResultKey(UserDict):
    """
    A hashable grouping of values used for a key
    """
    @typing.runtime_checkable
    class Owns(typing.Protocol):
        """Represents some type of object that has a result key as a property named 'key'"""
        @property
        def key(self) -> ResultKey:
            """The key that the object holds"""
    @classmethod
    def loads(cls, data: str) -> ResultKey:
        """
        Convert a string to a key

        Args:
            data: The string representation of a key

        Returns:
            A new key
        """
        data = json.loads(data)
        return cls.from_dict(data)

    @classmethod
    def load(cls, fp: typing.IO) -> ResultKey:
        """
        Read a key from a file like object (something that has a `.read` function)

        Args:
            fp: A file like object

        Returns:
            A new key
        """
        data = json.load(fp)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: typing.Mapping[str, typing.Any]) -> ResultKey:
        """
        Convert some mapping into a key

        Args:
            data: The mapping to convert

        Returns:
            A new key
        """
        return cls(**data)

    def __hash__(self) -> int:
        return hash(tuple((key, value) for key, value in self.items()))

    def __eq__(self, other: typing.Any) -> bool:
        if not isinstance(other, ResultKey):
            raise ValueError(f"Cannot compare {type(other)} with {type(other)}")
        return self.is_compatible(other) and hash(self) == hash(other)

    def __ne__(self, other: typing.Any) -> bool:
        if not isinstance(other, ResultKey):
            raise ValueError(f"Cannot compare {type(other)} with {type(other)}")
        return self.is_compatible(other) and hash(self) != hash(other)

    def __repr__(self) -> str:
        values = ', '.join([f"{key}={value}" for key, value in self.items()])
        return f"{self.__class__.__qualname__}({values})"

    def __str__(self) -> str:
        return ', '.join([f"{key}={value}" for key, value in self.items()])

    def is_compatible(self, other: typing.Any) -> bool:
        """
        Whether this key is compatible with another key

        Args:
            other: Another object, though ideally another key

        Returns:
            True if the data within the other key is compatible with this key
        """
        return isinstance(other, typing.Mapping) and set(self.keys()) == set(other.keys())

    @property
    def json(self) -> str:
        """
        The json representation of this data
        """
        return json.dumps(self)

    @property
    def dictionary(self) -> dict:
        """Convert this key to a standard dictionary"""
        return {**self}


class MetricResults:
    """
    A mapping thresholds to a variety of metrics and their values

    Expect all scores and thresholds within a MetricResults instance to pertain to a single location
    """
    def __init__(
        self,
        metric_scores: typing.Sequence[Score] = None,
        weight: NUMBER = 1,
    ):
        """
        Constructor

        Args:
            metric_scores: The scores to add
            weight: The significance of the scores that converge upon this point
        """
        self.__weight = weight or 1
        """The significance of the metrics evaluated at this key"""

        self.__scaled_value = 0
        """The aggregate for each score at this key in relation to the maximum score"""

        self.__total = 0
        """The total of all scaled values """
        self.__maximum_valid_score = 0
        self.__key: typing.Optional[ResultKey] = None

        self.__metric_scores = []
        """All scores"""

        self.add_scores(scores=metric_scores or [])

    @property
    def scores(self) -> typing.Iterator[Score]:
        """An iterator over all scores"""
        return iter(self.__metric_scores)

    @property
    def scores_by_metric(self) -> typing.Iterator[typing.Tuple[str, typing.Sequence[Score]]]:
        """All scores organized by their metric"""
        scores: typing.Dict[str, typing.List[Score]] = defaultdict(list)

        for score in self.valid_scores:
            scores[score.metric.name].append(score)

        return iter(scores.items())

    @property
    def scores_by_threshold(self) -> typing.Iterator[typing.Tuple[ThresholdMetadata, typing.Sequence[Score]]]:
        """All scores organized by their threshold"""
        scores: typing.Dict[ThresholdMetadata, typing.List[Score]] = defaultdict(list)

        for score in self.valid_scores:
            scores[score.threshold].append(score)

        return iter(scores.items())

    def keys_are_compatible(self, scores: typing.Sequence[Score]) -> bool:
        """
        Determine whether the keys in the collections of scores are all compatible with themselves and what is
        currently in the collection

        Args:
            scores: The scores to check

        Returns:
            True if the values are compatible with one another
        """
        score_keys: typing.Sequence[ResultKey] = list(map(lambda score: score.key, scores))

        if not all(key_one == key_two for key_one, key_two in itertools.combinations(score_keys, 2)):
            return False

        if self.__key:
            if not all(key.is_compatible(self.__key) for key in score_keys):
                return False

        return keys_are_uniform(scores, self.__metric_scores) if len(self) > 0 else True

    def to_dict(self) -> typing.Dict:
        """
        Convert the results into a dictionary that is easy to attach to other data
        """
        structured_results = {
            "weight": self.weight,
            "grade": self.grade_letter,
            "scaled_value": self.scaled_value,
            "key": self.key.dictionary,
            "scores": {
                metric_name: ScoreDescription(scores=scores).to_dict()
                for metric_name, scores in self.scores_by_metric
                if ScoreDescription(scores=scores).has_value
            }
        }

        return structured_results

    @property
    def has_value(self) -> bool:
        """Whether a value has been assigned to this metric"""
        has_weight = self.weight != 0 and not numpy.isnan(self.weight)
        has_total = not numpy.isnan(self.total)
        has_maximum_possible_score = self.maximum_valid_score != 0 and not numpy.isnan(self.maximum_valid_score)

        return has_weight and has_maximum_possible_score and has_total

    @property
    def key(self) -> ResultKey:
        """The identifier for where and what this set of results represents"""
        return self.__key

    @property
    def scaled_value(self) -> float:
        """
        Scales the overall value of all scores for this location as a fraction of its weight

        len(self.valid_scores)
                Σ       self.valid_scores[i].scaled_value
              i = 0
        --------------------------------------------------------  * self.weight
        len(self.valid_scores)
                Σ       self.valid_scores[i].metric.weight
              i = 0

        """
        return self.__scaled_value

    def columns(self, include_metadata: bool = None) -> typing.Mapping[str, typing.Sequence[typing.Any]]:
        """
        Creates a list of dictionaries that may be used to represent tabular fields

        Args:
            include_metadata: Whether to include metadata in regards to metric properties and used thresholds

        Returns:
            A list of dictionaries that may be used to represent tabular fields
        """
        if include_metadata is None:
            include_metadata = False

        columns: typing.Dict[str, typing.List[typing.Any]] = defaultdict(list)

        for threshold, scores in self.__results.items():  # type: ThresholdMetadata, typing.List[Score]
            for score in scores:
                columns['threshold_name'].append(threshold.name)
                columns['threshold_weight'].append(threshold.weight)
                columns['result'].append(score.value)
                columns['scaled_result'].append(score.scaled_value)
                columns['metric'].append(score.metric.name)
                columns['metric_weight'].append(score.metric.weight)

                if include_metadata:
                    columns['desired_metric_value'].append(score.metric.ideal_value)
                    columns['failing_metric_value'].append(score.metric.fails_on)
                    columns['metric_lower_bound'].append(score.metric.lower_bound)
                    columns['metric_upper_bound'].append(score.metric.upper_bound)
        return columns

    def to_dataframe(self, include_metadata: bool = None) -> polars.DataFrame:
        """
        Convert the results to a dataframe

        Args:
            include_metadata: Whether to include metadata about the metrics

        Returns:
            A dataframe representation of the metric results
        """
        columns: typing.Mapping[str, typing.Sequence[typing.Any]] = self.columns(include_metadata)
        return polars.DataFrame(data=columns)

    @property
    def valid_scores(self) -> typing.List[Score]:
        """
        A list of scores with sample sizes large enough to reflect reasonable calculations

        When including thresholds like record flows, there may be no observations or simulated values that ever cross
        the line. As a result, metrics can't be calculated and null values are rightfully returned. Considering null
        scores as perfect or failing will skew the results. If all entries in a truth table are in the
        'true negative' cell, is the probability of detection right or wrong? It's neither.  This list will grant
        all scores appropriate for final calculations.
        """
        valid_scores: typing.List[Score] = [
            score
            for score in self.__metric_scores
            if not (
                numpy.isnan(score.sample_size)
                or numpy.isnan(score.value)
                or score.sample_size == 0
            )
        ]
        return valid_scores

    @property
    def maximum_valid_score(self) -> NUMBER:
        """
        The maximum value that the total of all underlying scores could return
        """
        return self.__maximum_valid_score

    @property
    def total(self) -> NUMBER:
        """
        The raw total score of all metrics
        """
        return self.__total

    @property
    def grade(self) -> NUMBER:
        """
        The score in terms of a standard 0-100 grade curve
        """
        return self.scaled_value * 100.0

    @property
    def grade_letter(self) -> str:
        """The performance of the metrics in terms of a school-like grade scale"""
        if self.grade < 60:
            return "F"
        if self.grade < 63:
            return "D-"
        if self.grade < 67:
            return "D"
        if self.grade < 70:
            return "D+"
        if self.grade < 73:
            return "C-"
        if self.grade < 77:
            return "C"
        if self.grade < 80:
            return "C+"
        if self.grade < 83:
            return "B-"
        if self.grade < 87:
            return "B"
        if self.grade < 90:
            return "B+"
        if self.grade < 93:
            return "A-"
        if self.grade < 97:
            return "A"

        return "A+"

    @property
    def weight(self) -> int:
        """
        The significance of the metric being represented at the common key
        """
        return self.__weight

    def add_scores(self, scores: typing.Sequence[Score]):
        """
        Add a collection of scores to the results. Ensures that the values are valid, adds them to the collection and
        recalculates the aggregate values

        Args:
            scores: The scores for the metrics to add
        """
        self.keys_are_compatible(scores=scores)
        self.__metric_scores.extend(scores)
        self.__recalculate()

    def __recalculate(self):
        """
        Update internal values for aggregate scores based on stored score values

        - The total is the sum of the scaled values of each metric
        - The maximum valid score is the sum of the weight of each metric
        - The scaled value is the degree to which the total met the maximum score multiplied by this set of metric's
          significance
        """
        descriptions: typing.Sequence[ScoreDescription] = [
            ScoreDescription(scores)
            for _, scores in self.scores_by_metric
        ]
        self.__total = sum(map(lambda description: description.scaled_value, descriptions))
        self.__maximum_valid_score = sum(map(lambda description: description.weight, descriptions))
        self.__scaled_value = (self.__total / self.__maximum_valid_score) * self.weight

    def __iter__(self) -> typing.Iterator[Score]:
        return iter(self.__metric_scores)

    def __str__(self) -> str:
        return f"Metric Results: {self.scaled_value} ({self.total} out of {self.maximum_valid_score})"

    def __repr__(self):
        return str(self)

    def __len__(self) -> int:
        return len(self.__metric_scores)


class ScoringScheme:
    """
    A definition for how to score metrics
    """
    def __init__(
        self,
        metrics: typing.Sequence[MetricExpression] = None,
        communicators: CommunicatorGroup = None
    ):
        self.__metrics = metrics or []
        self.__communicators = communicators or CommunicatorGroup()

    def score(
        self,
        pairs: polars.DataFrame,
        thresholds: typing.Sequence[ThresholdMetadata] = None,
        metadata: dict = None
    ) -> typing.Mapping[ResultKey, MetricResults]:
        """
        Run all of the metrics and return the results

        Args:
            pairs: Observed, Predicted, and Threshold values to be evaluated
            thresholds: Metadata about the thresholds to evaluate
            metadata: Additional metadata to attach to the runtime messaging

        Returns:
            Organized results for each threshold for each metric for each location
        """
        if len(self.__metrics) == 0:
            raise ValueError(
                "No metrics were attached to the scoring scheme - values cannot be scored and aggregated"
            )

        results: typing.Dict[ResultKey, typing.List[Score]] = defaultdict(list)

        for metric in self.__metrics:  # type: MetricExpression
            self.__communicators.info(f"Calling {metric.name}", verbosity=Verbosity.LOUD, publish=True)
            scores: typing.Sequence[Score] = []
            for threshold in thresholds:
                scores = metric.evaluate(
                    data=pairs,
                    threshold=threshold
                )

                for score in scores:
                    results[score.key].append(score)

            if scores is not None and len(scores) > 0 and self.__communicators.send_all():
                message = {
                    "metric": metric.name,
                    "description": metric.get_description(),
                    "weight": metric.weight,
                    "scores": [score.to_dict() for score in scores]
                }

                if metadata:
                    message['metadata'] = metadata

                self.__communicators.write(reason="metric", data=message, verbosity=Verbosity.ALL)

        metric_results: typing.Mapping[ResultKey, MetricResults] = {
            key: MetricResults(metric_scores=scores_per_key)
            for key, scores_per_key in results.items()
        }
        return metric_results
