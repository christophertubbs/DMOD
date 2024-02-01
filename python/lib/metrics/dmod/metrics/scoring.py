#!/usr/bin/env python
from __future__ import annotations

import itertools
import logging
import os
import typing
import string
import abc
import re

from collections import defaultdict
from collections import abc as abstract_collections
from datetime import datetime

from math import inf as infinity

from typing_extensions import ParamSpec
from typing_extensions import Concatenate
from typing_extensions import Annotated

import pandas
import numpy
import numpy.typing

from arch import bootstrap

from arviz import hdi

import dmod.core.common as common

from .common import highest_density_interval
from .distributor import SynchronousWorkDistributor
from .distributor import ThreadedWorkDistributor
from .distributor import WorkDistributionProtocol
from .threshold import Threshold
from .communication import Verbosity
from .communication import Communicator
from .communication import CommunicatorGroup

ARGS_AND_KWARGS = ParamSpec("ARGS_AND_KWARGS")
NUMBER = typing.Union[int, float]

METRIC = typing.Callable[
    Concatenate[
        pandas.DataFrame,
        pandas.DataFrame,
        typing.Sequence[Threshold],
        ARGS_AND_KWARGS
    ],
    NUMBER
]

SCORE_FUNCTION = typing.Callable[
    Concatenate[
        pandas.DataFrame,
        str,
        str,
        typing.Optional[typing.Sequence[Threshold]],
        ARGS_AND_KWARGS
    ],
    "Scores"
]
"""Function used to score results - `f(pairs, obs label, forecast label, thresholds, *args, **kwargs)`"""

BOOTSTRAP_CLASS = typing.TypeVar("BOOTSTRAP_CLASS", bound=bootstrap.IIDBootstrap, covariant=True)
DEFAULT_BOOTSTRAP = bootstrap.StationaryBootstrap

NUMERIC_OPERATOR = typing.Callable[[NUMBER, NUMBER, typing.Optional[NUMBER]], NUMBER]
NUMERIC_TRANSFORMER = typing.Callable[[NUMBER], NUMBER]
NUMERIC_FILTER = typing.Callable[[NUMBER, NUMBER], bool]
FRAME_FILTER = typing.Callable[[pandas.DataFrame], pandas.DataFrame]


EPSILON = 0.0001

WHITESPACE_PATTERN = re.compile(f"[{string.whitespace}]+")


def scale_value(metric: Metric, raw_value: NUMBER) -> NUMBER:
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


class Metric(abc.ABC, SCORE_FUNCTION):
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
        if weight is None or not (isinstance(weight, int) or isinstance(weight, float)) or numpy.isnan(weight):
            raise ValueError("Weight must be supplied and must be numeric")

        self.__lower_bound = lower_bound if lower_bound is not None else -infinity
        self.__upper_bound = upper_bound if upper_bound is not None else infinity
        self.__ideal_value = ideal_value if ideal_value is not None else numpy.nan
        self.__weight = weight
        self.__greater_is_better = greater_is_better if greater_is_better is not None else True
        self.__failure = failure

    @classmethod
    @abc.abstractmethod
    def get_descriptions(cls):
        """
        Returns:
            A description of how the metric works and how it's supposed be be interpreted
        """
        pass

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

    def _add_to_kwargs(
        self,
        pairs: pandas.DataFrame,
        observed_value_label: str,
        predicted_value_label: str,
        thresholds: typing.Sequence[Threshold] = None,
        *args,
        **kwargs
    ) -> typing.Mapping:
        return kwargs

    def __call__(
        self,
        pairs: pandas.DataFrame,
        observed_value_label: str,
        predicted_value_label: str,
        thresholds: typing.Sequence[Threshold] = None,
        communicators: CommunicatorGroup = None,
        bootstrap_class: BOOTSTRAP_CLASS = None,
        *args,
        **kwargs
    ) -> Scores:
        if not thresholds:
            thresholds = [Threshold.default()]

        kwargs = self._add_to_kwargs(
            pairs=pairs,
            observed_value_label=observed_value_label,
            predicted_value_label=predicted_value_label,
            thresholds=thresholds,
            *args,
            **kwargs
        )

        scores: typing.List[Score] = list()

        for threshold in thresholds:
            filtered_pairs = threshold(pairs)

            result = self.score_threshold(
                filtered_pairs=filtered_pairs,
                threshold=threshold,
                observed_value_label=observed_value_label,
                predicted_value_label=predicted_value_label,
                communicators=communicators,
                *args, **kwargs
            )

            if len(filtered_pairs) > 3:
                time_before_interval_generation = datetime.now()
                interval = self.generate_bootstrap_intervals(
                    filtered_pairs=filtered_pairs,
                    threshold=threshold,
                    observed_value_label=observed_value_label,
                    predicted_value_label=predicted_value_label,
                    communicators=communicators,
                    bootstrap_class=bootstrap_class,
                    *args,
                    **kwargs
                )
                print(f"It took {datetime.now() - time_before_interval_generation} to generate an interval for {self.name}")
            else:
                interval = None

            score = Score(
                metric=self,
                value=result,
                interval=interval,
                threshold=threshold,
                sample_size=len(filtered_pairs)
            )

            scores.append(score)

        return Scores(metric=self, scores=scores)

    def generate_bootstrap_intervals(
        self,
        filtered_pairs: pandas.DataFrame,
        threshold: Threshold,
        observed_value_label: str,
        predicted_value_label: str,
        communicators: CommunicatorGroup = None,
        bootstrap_class: BOOTSTRAP_CLASS = None,
        *args,
        **kwargs
    ) -> typing.Optional[typing.Sequence[float]]:
        if len(filtered_pairs) < 5:
            return None

        if bootstrap_class is None:
            bootstrap_class = DEFAULT_BOOTSTRAP

        bootstrap_type = "stationary" if bootstrap_class == bootstrap.StationaryBootstrap else "circular"

        predicted_vs_observed = filtered_pairs[[observed_value_label, predicted_value_label]]

        try:
            block_length = bootstrap.optimal_block_length(predicted_vs_observed.values)[bootstrap_type].max()
        except Exception as e:
            logging.error("Could not establish the block length for a bootstrapping operation")
            raise

        threshold_bootstrap = bootstrap_class(block_length, filtered_pairs)

        before_bootstrap_application = datetime.now()
        metric_distribution: numpy.ndarray[Score] = threshold_bootstrap.apply(
            lambda pairs: self.score_threshold(
                filtered_pairs=pairs,
                threshold=threshold,
                observed_value_label=observed_value_label,
                predicted_value_label=predicted_value_label,
                communicators=communicators,
                *args,
                **kwargs
            )
        )
        print(f"It took {datetime.now() - before_bootstrap_application} to bootstrap data for {self.name}")

        before_hdi = datetime.now()
        interval = hdi(
            metric_distribution.flatten(),
            hdi_prob=0.95
        )
        print(f"It took {datetime.now() - before_hdi} to develop the hdi interval")

        return interval.tolist()

    @abc.abstractmethod
    def score_threshold(
        self,
        filtered_pairs: pandas.DataFrame,
        threshold: Threshold,
        observed_value_label: str,
        predicted_value_label: str,
        communicators: CommunicatorGroup = None,
        *args,
        **kwargs
    ) -> float:
        pass

    @classmethod
    def is_categorical(cls) -> bool:
        return False

    @property
    def details(self) -> typing.Dict[str, typing.Any]:
        return {
            "name": self.name,
            "ideal_value": self.ideal_value,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "is_categorical": self.is_categorical(),
            "fails_on": self.fails_on,
            "weight": self.weight
        }

    def serialize(self) -> typing.Dict[str, typing.Any]:
        return {
            "name": self.name,
            "weight": self.weight
        }

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return "Metric(name=" + self.name + ")"


class Score:
    def __init__(
        self,
        metric: Metric,
        value: NUMBER,
        interval: typing.Sequence[float] = None,
        threshold: Threshold = None,
        sample_size: int = None
    ):
        self.__metric = metric
        self.__value = value
        self.__threshold = threshold or Threshold.default()
        self.__sample_size = sample_size or numpy.nan
        self.__interval = interval

    @property
    def value(self) -> NUMBER:
        return self.__value

    @property
    def interval(self) -> typing.Optional[numpy.ndarray]:
        """
        The range within which there is a confidence of 95% where the most accurate value of this score resides
        """
        if self.__interval is None:
            return None

        value = numpy.array(self.__interval)
        assert value.shape == (2,)

        return value

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
        raw_scaled_value = scale_value(self.__metric, self.__value)

        if numpy.isnan(raw_scaled_value):
            print(
                f"{self.__metric.name} score for the {self.__threshold.name} threshold has a null scaled value based on a value of {self.__value} and information from {os.linesep}"
                f"{self.__metric.details}"
            )

        return raw_scaled_value * self.__threshold.weight

    @property
    def scaled_interval(self) -> typing.Optional[numpy.ndarray]:
        """
        The interval for the score with each value properly oriented within the [0, 1] scale
        """
        new_bounds = [scale_value(self.__metric, bound) for bound in self.interval]

        if not all([not numpy.isnan(bound) for bound in new_bounds]):
            return None

        return numpy.array(new_bounds)

    @property
    def metric(self) -> Metric:
        return self.__metric

    @property
    def threshold(self) -> Threshold:
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
        elif numpy.isnan(self.__metric.fails_on) and numpy.isnan(self.__value):
            return True
        elif numpy.isnan(self.__metric.fails_on):
            return False

        difference = self.__value - self.__metric.fails_on
        difference = abs(difference)

        failed = difference < EPSILON

        return bool(failed)

    @property
    def sample_size(self):
        return self.__sample_size

    def to_dict(self) -> dict:
        return {
            "value": common.truncate(self.value, 2),
            "scaled_value": common.truncate(self.scaled_value, 2),
            "sample_size": common.truncate(self.sample_size, 2),
            "interval": self.__interval,
            "scaled_interval": self.scaled_interval.tolist() if self.scaled_interval else None,
            "failed": self.failed,
            "weight": self.threshold.weight,
            "threshold": self.threshold.name,
            "grade": self.grade,
        }

    def __bool__(self) -> bool:
        return self.__sample_size

    def __len__(self):
        return self.__sample_size

    def __str__(self) -> str:
        return f"{self.metric} => ({self.threshold}: {self.scaled_value})"

    def __repr__(self) -> str:
        return self.__str__()


class ScoreDescription:
    """
    A simple class used to help organize finalized score data

    Manages the formatting of all scores for an individual Metric
    """
    def __init__(self, scores: typing.Sequence[Score]):
        self.__total: int = 0
        self.__maximum_metric_value: int = 0
        self.__weight: typing.Optional[int] = None
        self.__thresholds: typing.Dict[str, dict] = dict()
        self.__scaled_value: int = 0
        self.__metric_name = None
        self.__interval: typing.Optional[numpy.ndarray] = None
        self.__scaled_interval: typing.Optional[numpy.ndarray] = None

        self.__add_scores(scores)

    @property
    def total_interval(self) -> typing.Optional[numpy.ndarray]:
        return self.__interval

    def __calculate_intervals(self, scores: typing.Sequence[Score]):
        self.__interval = sum([score.interval for score in scores if score.interval])

        threshold_weights = [score.threshold.weight for score in scores if score.interval]
        self.__scaled_interval = numpy.average(
            [score.scaled_interval for score in scores if score.scaled_interval],
            axis=0,
            weights=threshold_weights
        )

    @property
    def scaled_interval(self) -> typing.Optional[numpy.ndarray]:
        return self.__scaled_interval

    def __add_scores(self, scores: typing.Sequence[Score]):
        for score in scores:
            if self.__weight is None:
                self.__weight = score.metric.weight
                self.__metric_name = score.metric.name

            self.__thresholds[score.threshold.name] = score.to_dict()

            if not numpy.isnan(score.scaled_value):
                self.__maximum_metric_value += score.threshold.weight
                self.__total += score.scaled_value

        if self.has_value:
            scale_factor = self.__total / self.__maximum_metric_value
            self.__scaled_value = scale_factor * self.__weight

            self.__calculate_intervals(scores)

    def to_dict(self) -> dict:
        return {
            "name": self.__metric_name,
            "total": self.__total,
            "total_interval": self.total_interval,
            "maximum_possible_value": self.__maximum_metric_value,
            "scaled_value": self.__scaled_value,
            "scaled_interval": self.scaled_interval,
            "thresholds": self.__thresholds,
            "weight": self.__weight
        }

    @property
    def has_value(self) -> bool:
        total_has_value = self.__total != 0 and not numpy.isnan(self.__total)
        has_maximum_value = self.__maximum_metric_value !=0 and not numpy.isnan(self.__maximum_metric_value)
        has_weight = self.__weight != 0 and not numpy.isnan(self.__weight)

        return has_weight and total_has_value and has_maximum_value

    @property
    def name(self) -> str:
        return self.__metric_name

    @property
    def weight(self) -> int:
        return self.__weight

    @property
    def value(self) -> float:
        return self.__total

    @property
    def scaled_value(self) -> float:
        return self.__scaled_value

    @property
    def maximum_value(self) -> float:
        return self.__maximum_metric_value

    @property
    def thresholds(self) -> typing.Dict[str, dict]:
        return self.__thresholds

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.name}: {self.__total} out of {self.maximum_value}"


class Scores(abstract_collections.Sequence[Score]):
    def __len__(self) -> int:
        return len(self.__results)

    def __init__(self, metric: Metric, scores: typing.Sequence[Score] = None):
        self.__metric = metric

        if scores is None:
            scores = []

        self.__results = {
            score.threshold: score
            for score in scores
        }

    def add(self, score: Score):
        if not isinstance(score, Score):
            raise TypeError(
                f"Cannot add a '{score.__class__.__name__ if score is not None else None}' "
                f"object to a scores collection"
            )

        if score.metric != self.metric:
            raise ValueError(f"Cannot add a score for {score.metric} to a collection of {self.metric} scores")

        if score.threshold in self.__results:
            raise ValueError(f"There is already a value for the '{score.threshold}' threshold in this score collection")

        self.__results[score.threshold] = score

    @property
    def metric(self) -> Metric:
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
            return 0

        return sum([
            score.scaled_value
            for score in self
            if not numpy.isnan(score.sample_size)
               and score.sample_size > 0
        ])

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
        scores = [
            score.scaled_value
            for score in self
            if not numpy.isnan(score.sample_size)
                and score.sample_size > 0
        ]

        weights = [
            score.threshold.weight
            for score in self
            if not numpy.isnan(score.sample_size)
                and score.sample_size > 0
        ]

        try:
            average = numpy.average(scores, weights=weights)
            return average
        except:
            return numpy.nan

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

    @property
    def scaled_interval(self) -> typing.Sequence[float]:
        return highest_density_interval([
            score.scaled_value
            for score in self
            if score.sample_size > 0
        ])

    @property
    def interval(self) -> typing.Sequence[float]:
        return highest_density_interval([
            score.value
            for score in self
            if score.sample_size > 0
        ])

    def to_dict(self) -> dict:
        score_representation = {
            "total": self.total,
            "interval": self.interval,
            "scaled_value": common.truncate(self.scaled_value, 2),
            "scaled_interval": self.scaled_interval,
            "grade": "{:.2f}%".format(self.performance * 100) if not numpy.isnan(self.performance) else None,
            "scores": dict()
        }

        for threshold, score in self.__results.items():  # type: Threshold, Score
            score_representation['scores'][str(threshold)] = score.to_dict()

        return score_representation

    @property
    def has_data(self) -> bool:
        return any([
            score.sample_size > 0 for score in self
        ])

    def __getitem__(self, key: typing.Union[str, Threshold]) -> Score:
        if isinstance(key, Threshold):
            key = key.name

        for threshold, score in self.__results.items():
            if threshold.name == key:
                return score

        raise ValueError(f"There is not a score for '{key}'")

    def __setitem__(self, key: Threshold, value: Score):
        if not isinstance(key, Threshold):
            raise TypeError(f"Cannot assign a score to a Scores collection with a key that is not a threshold")

        if not isinstance(value, Score):
            raise TypeError(f"Cannot add a '{value.__class__.__name__}' object to a Scores collection")

        self.add(value)

    def __bool__(self):
        return self.has_data

    def __iter__(self) -> typing.Iterator[Score]:
        return iter(self.__results.values())

    def __str__(self) -> str:
        return f"[{self.metric.name}] " + ", ".join([str(score) for score in self.__results])

    def __repr__(self) -> str:
        return self.__str__()


class MetricResults:
    """
    A mapping thresholds to a variety of metrics and their values

    Expect all scores and thresholds within a MetricResults instance to pertain to a single location
    """
    def __init__(
        self,
        name: str = None,
        weight: NUMBER = None
    ):
        self.__name = name
        self.__weight = weight or 1
        self.__metrics: typing.Dict[Metric, Scores] = {}

    @property
    def name(self) -> typing.Optional[str]:
        return self.__name

    @property
    def scaled_interval(self) -> typing.Sequence[float]:
        interval = highest_density_interval([
            Scores(metric, scores).scaled_value
            for metric, scores in self.__metrics.items()
        ])
        return interval

    def to_dict(self) -> typing.Dict:
        structured_results = {
            "interval": self.scaled_interval,
            "weight": self.weight,
            "grade": self.grade,
            "scaled_value": self.scaled_value,
            "scores": dict()
        }

        for metric, scores in self.__metrics.items():  # type: Metric, Scores
            description = ScoreDescription(scores)

            if description.has_value:
                structured_results['scores'][metric.name] = scores.to_dict()

        return structured_results

    @property
    def has_value(self) -> bool:
        has_weight = self.weight != 0 and not numpy.isnan(self.weight)
        has_total = self.total != 0 and not numpy.isnan(self.total)
        has_maximum_possible_value = self.maximum_valid_score != 0 and not numpy.isnan(self.maximum_valid_score)

        return has_weight and has_maximum_possible_value and has_total

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
        return numpy.average(
            [
                scores.performance
                for scores in self.values()
            ],
            weights=[
                scores.metric.weight
                for scores in self.values()
            ]
        )

    def rows(self, include_metadata: bool = None) -> typing.List[typing.Dict[str, typing.Any]]:
        """
        Creates a list of dictionaries that may be used to represent tabular fields

        Args:
            include_metadata: Whether to include metadata in regards to metric properties and used thresholds

        Returns:
            A list of dictionaries that may be used to represent tabular fields
        """
        if include_metadata is None:
            include_metadata = False

        rows = list()

        for metric, scores in self.__metrics.items():
            threshold_values = metric.threshold.value

            if isinstance(threshold_values, pandas.Series):
                threshold_values = threshold_values.tolist()

            threshold_value_is_sequence = isinstance(metric.threshold.value, typing.Sequence)
            threshold_value_is_sequence &= not isinstance(metric.threshold.value, str)

            threshold_value = threshold_values[0] if threshold_value_is_sequence else metric.threshold.value
            metric_rows: typing.List[dict] = list()

            for score in scores:
                row_values = dict()
                row_values['threshold_name'] = metric.threshold.name
                row_values['threshold_weight'] = metric.threshold.weight
                row_values['result'] = score.value
                row_values['scaled_result'] = score.scaled_value
                row_values['metric'] = metric.name
                row_values['metric_weight'] = metric.weight
                row_values['interval_lower_bound'] = score.interval[0]
                row_values['interval_upper_bound'] = score.interval[1]
                row_values['scaled_interval_lower_bound'] = score.scaled_interval[0]
                row_values['scaled_interval_upper_bound'] = score.scaled_interval[1]

                if include_metadata:
                    row_values['threshold_value'] = threshold_value
                    row_values['desired_metric_value'] = metric.ideal_value
                    row_values['failing_metric_value'] = metric.fails_on
                    row_values['metric_lower_bound'] = metric.lower_bound
                    row_values['metric_upper_bound'] = metric.upper_bound

                metric_rows.append(row_values)

            rows.extend(metric_rows)
        return rows

    def to_dataframe(self, include_metadata: bool = None) -> pandas.DataFrame:
        rows = self.rows(include_metadata)
        return pandas.DataFrame(rows)

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
            for score in self.scores
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
        all_weight = sum([
            scores.metric.weight
            for scores in self.values()
            if not numpy.isnan(scores.total)
        ])
        return all_weight

    @property
    def total(self) -> NUMBER:
        all_scaled_values = sum([
            scores.scaled_value
            for scores in self.values()
            if not numpy.isnan(scores.scaled_value)
        ])
        return all_scaled_values

    @property
    def performance(self) -> NUMBER:
        return (self.total / self.maximum_valid_score) * self.weight

    @property
    def grade(self) -> NUMBER:
        return self.performance * 100.0

    def keys(self) -> typing.KeysView:
        return self.__metrics.keys()

    def values(self) -> typing.ValuesView:
        return self.__metrics.values()

    def items(self) -> typing.ItemsView:
        return self.__metrics.items()

    @property
    def weight(self):
        return self.__weight

    @property
    def metrics(self) -> typing.Sequence[Metric]:
        return [
            metric
            for metric in self.keys()
        ]

    @property
    def scores(self) -> typing.Sequence[Score]:
        master_list: typing.List[Score] = list()

        for scores in self.values():
            master_list.extend(scores)

        return master_list

    def add_scores(self, scores: Scores):
        for score in scores:  # type: Score
            if score.metric not in self.__metrics:
                self.__metrics[score.metric] = Scores(score.metric)
            self.__metrics[score.metric].add(score)

    def __getitem__(self, metric_name: str) -> typing.Sequence[Score]:
        result_key = None

        for metric in self.__metrics.keys():
            if metric.name.lower() == metric_name.lower():
                result_key = metric
                break

        if result_key:
            return self.__metrics[result_key]

        available_metrics = [metric.name for metric in self.metrics]

        raise KeyError(
            f"There are no thresholds named '{metric_name}'. Available keys are: {', '.join(available_metrics)}"
        )

    def __iter__(self) -> typing.Iterator[typing.Tuple[Threshold, Scores]]:
        return iter(self.__metrics.items())

    def __str__(self) -> str:
        return f"Metric Results: {self.scaled_value} ({self.total} out of {self.maximum_valid_score})"

    def __repr__(self):
        return str(self)


def run_metric(
    pairs: pandas.DataFrame,
    observed_value_label: str,
    predicted_value_label: str,
    metric: Metric,
    current_threshold: Threshold,
    metadata: dict = None,
    communicators: CommunicatorGroup = None,
    calculate_interval: bool = None,
    *args,
    **kwargs
) -> Scores:
    # TODO: This should call the metric with the current threshold - metrics currently only accept sets of
    #  thresholds for later slicing and dicing. This should instead send a single threshold so that thresholds
    #  aren't repeatedly calculated
    if communicators:
        communicators.info(f"Calling {metric.name}", verbosity=Verbosity.LOUD, publish=True)

    scores = metric(
        pairs=pairs,
        observed_value_label=observed_value_label,
        predicted_value_label=predicted_value_label,
        thresholds=current_threshold,
        *args,
        **kwargs
    )

    if communicators and communicators.send_all():
        message = {
            "metric": scores.metric.name,
            "description": scores.metric.get_descriptions(),
            "weight": scores.metric.weight,
            "total": scores.total,
            "scores": scores.to_dict()
        }

        if metadata:
            message['metadata'] = metadata

        communicators.write(reason="metric", data=message, verbosity=Verbosity.ALL)

    return scores


def run_legacy_metric(
    metric: Metric,
    pairs: pandas.DataFrame,
    observed_value_label: str,
    predicted_value_label: str,
    thresholds: typing.Sequence[Threshold],
    communicators: CommunicatorGroup = None,
    metadata: dict = None,
    calculate_interval: bool = None,
    *args,
    **kwargs
) -> Scores:
    if communicators:
        communicators.info(f"Calling {metric.name}", verbosity=Verbosity.LOUD, publish=True)

    scores = metric(
        pairs=pairs,
        observed_value_label=observed_value_label,
        predicted_value_label=predicted_value_label,
        thresholds=thresholds,
        *args,
        **kwargs
    )

    if communicators and communicators.send_all():
        message = {
            "metric": scores.metric.name,
            "description": scores.metric.get_descriptions(),
            "weight": scores.metric.weight,
            "total": scores.total,
            "scores": scores.to_dict()
        }

        if metadata:
            message['metadata'] = metadata

        communicators.write(reason="metric", data=message, verbosity=Verbosity.ALL)

    return scores


class ScoringScheme(object):
    def __init__(
        self,
        metrics: typing.Sequence[Metric] = None,
        communicators: typing.Union[typing.Dict[str, Communicator], typing.Sequence[Communicator], CommunicatorGroup] = None,
        name: str = None,
        calculate_interval: bool = None
    ):
        self.__metrics = metrics or list()
        self.__communicators = CommunicatorGroup(communicators=communicators)
        self.__name = name
        self.__calculate_interval = bool(calculate_interval)

    def serialize(self) -> typing.Dict[str, typing.Any]:
        return {
            "metrics": [
                metric.serialize()
                for metric in self.__metrics
            ],
            "communicators": self.__communicators.serialize(),
            "name": self.__name,
            "calculate_interval": self.__calculate_interval
        }

    async def score_asynchronously(
        self,
        pairs: pandas.DataFrame,
        observed_value_label: str,
        predicted_value_label: str,
        thresholds: typing.Sequence[Threshold] = None,
        weight: NUMBER = None,
        metadata: dict = None,
        distributor: WorkDistributionProtocol = None,
        *args,
        **kwargs
    ) -> MetricResults:
        if len(self.__metrics) == 0:
            raise ValueError(
                "No metrics were attached to the scoring scheme - values cannot be scored and aggregated"
            )

        run_thresholds_individually = False

        weight = 1 if not weight or numpy.isnan(weight) else weight

        results = MetricResults(weight=weight)

        if thresholds is None:
            thresholds = [Threshold.default()]

        if distributor is None:
            distributor = ThreadedWorkDistributor()

        if run_thresholds_individually:
            wrapper_function = run_metric

            threshold_pairs = {
                threshold: threshold(pairs)
                for threshold in thresholds
            }

            parameters = [
                {
                    "pairs": threshold_and_filtered_pairs[1],
                    "observed_value_label": observed_value_label,
                    "predicted_value_label": predicted_value_label,
                    "metric": metric,
                    "current_threshold": threshold_and_filtered_pairs[0],
                    "metadata": metadata,
                    "communicators": self.__communicators,
                    "calculate_interval": self.__calculate_interval
                }
                for metric, threshold_and_filtered_pairs in itertools.product(self.__metrics, threshold_pairs.items())
            ]
        else:
            wrapper_function = run_legacy_metric

            parameters = [
                {
                    "pairs": pairs,
                    "observed_value_label": observed_value_label,
                    "predicted_value_label": predicted_value_label,
                    "metric": metric,
                    "thresholds": thresholds,
                    "metadata": metadata,
                    "communicators": self.__communicators,
                    "calculate_interval": self.__calculate_interval
                }
                for metric in self.__metrics
            ]

        metric_scores = await distributor.perform_asynchronously(
            function=wrapper_function,
            parameters=parameters,
            *args,
            **kwargs
        )

        for scores in metric_scores:
            results.add_scores(scores)

        return results

    def score(
        self,
        pairs: pandas.DataFrame,
        observed_value_label: str,
        predicted_value_label: str,
        thresholds: typing.Sequence[Threshold] = None,
        weight: NUMBER = None,
        metadata: dict = None,
        distributor: WorkDistributionProtocol = None,
        *args,
        **kwargs
    ) -> MetricResults:
        if len(self.__metrics) == 0:
            raise ValueError(
                "No metrics were attached to the scoring scheme - values cannot be scored and aggregated"
            )

        run_thresholds_individually = False

        weight = 1 if not weight or numpy.isnan(weight) else weight

        results = MetricResults(weight=weight)

        if thresholds is None:
            thresholds = [Threshold.default()]

        if distributor is None:
            distributor = SynchronousWorkDistributor()

        if run_thresholds_individually:
            wrapper_function = run_metric

            threshold_pairs = {
                threshold: threshold(pairs)
                for threshold in thresholds
            }

            parameters = [
                {
                    "pairs": threshold_and_filtered_pairs[1],
                    "observed_value_label": observed_value_label,
                    "predicted_value_label": predicted_value_label,
                    "metric": metric,
                    "current_threshold": threshold_and_filtered_pairs[0],
                    "metadata": metadata,
                    "communicators": self.__communicators,
                    "calculate_interval": self.__calculate_interval
                }
                for metric, threshold_and_filtered_pairs in itertools.product(self.__metrics, threshold_pairs.items())
            ]
        else:
            wrapper_function = run_legacy_metric

            parameters = [
                {
                    "pairs": pairs,
                    "observed_value_label": observed_value_label,
                    "predicted_value_label": predicted_value_label,
                    "metric": metric,
                    "thresholds": thresholds,
                    "metadata": metadata,
                    "communicators": self.__communicators,
                    "calculate_interval": self.__calculate_interval
                }
                for metric in self.__metrics
            ]

        metric_scores = distributor.perform(function=wrapper_function, parameters=parameters, *args, **kwargs)

        for scores in metric_scores:
            results.add_scores(scores)

        return results
