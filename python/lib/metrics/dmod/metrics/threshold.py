"""
Defines formalized Threshold objects that serve as functions for subsetting data
"""
import typing

from math import inf as infinity
from operator import ge

import polars
import numpy

NUMBER = typing.Union[int, float, polars.Series]

PolarsData = typing.Union[polars.DataFrame, polars.Series]

NUMERIC_FILTER = typing.Callable[[NUMBER, NUMBER], bool]
FRAME_FILTER = typing.Callable[[PolarsData], PolarsData]
INDEX_TRANSFORMATION_FUNCTION = typing.Callable[[PolarsData, typing.Optional[str], typing.Optional[str]], PolarsData]


def value_is_indexible(value) -> bool:
    is_indexible = not isinstance(value, (str, bytes))
    is_indexible &= hasattr(value, "__getitem__")

    return is_indexible


class Operators(object):
    """
    A collection of stock comparators that form threshold operators
    """

    @staticmethod
    def get_method(name: str) -> NUMERIC_FILTER:
        """
        Gets a thresholding function based on a name representation

        Supported Operators:
        * ">", 'greater_than', 'greater than'
        * ">=", 'greater_than_or_equal', 'greater than or equal', 'greater than or equal to'
        * "<", 'less_than', 'less than'
        * "<=", "less_than_or_equal", 'less than or equal', 'less than or equal to'
        * is', '=', '==', 'equal', 'equals', 'equal to'

        Args:
            name: The name of the operator to use

        Returns:

        """
        name = name.lower()

        if name in [">", 'greater_than']:
            return Operators.greater_than

        if name in [">=", 'greater_than_or_equal']:
            return Operators.greater_than_or_equal

        if name in ["<", 'less_than']:
            return Operators.less_than

        if name in ["<=", "less_than_or_equal"]:
            return Operators.less_than_or_equal

        if name in ['is', '=', '==', 'equal', 'equals']:
            return Operators.equal

        raise ValueError(f"{name} is not a valid threshold operator")

    @staticmethod
    def greater_than(first, second) -> bool:
        return first > second

    @staticmethod
    def greater_than_or_equal(first, second) -> bool:
        return first >= second

    @staticmethod
    def equal(first, second) -> bool:
        return first == second

    @staticmethod
    def less_than(first, second) -> bool:
        return first < second

    @staticmethod
    def less_than_or_equal(first, second) -> bool:
        return first <= second

    def __init__(self, operator_name: str):
        self.__operator_function: NUMERIC_FILTER = Operators.get_method(operator_name)

    def __call__(self, first: NUMBER, second: NUMBER) -> bool:
        return self.__operator_function(first, second)


class ValueFilter(typing.Callable[[PolarsData], PolarsData]):
    def __init__(
        self,
        operator: NUMERIC_FILTER,
        threshold_value: NUMBER,
        observation_key: str = None,
        prediction_key: str = None
    ):
        """

        Args:
            operator:
            threshold_value:
            observation_key:
            prediction_key:
        """
        self._operator = operator
        self._observation_key = observation_key
        self._observation_column: polars.Expr = polars.col(observation_key)
        self._prediction_key = prediction_key
        self._prediction_column: polars.Expr = polars.col(prediction_key)

        threshold_is_indexible = value_is_indexible(threshold_value)

        if threshold_is_indexible and len(threshold_value) == 1:
            if isinstance(threshold_value, polars.Series):
                threshold_value = threshold_value.values[0]
            else:
                threshold_value = threshold_value[0]
            threshold_is_indexible = False

        self._threshold_value = threshold_value
        self._threshold_is_indexible = threshold_is_indexible

    def filter_series(self, series: polars.Series) -> polars.Series:
        """
        Apply the threshold to a single series

        Args:
            series: The series that should be thresholded

        Returns:
            A series containing only the values that fit the given threshold
        """
        if isinstance(self._threshold_value, polars.Series):
            joined_data = series.to_frame().join(self._threshold_value)
            filtered_series = self._operator(joined_data[series.name], joined_data[self._threshold_value.name])
        else:
            filtered_series = self._operator(series, self._threshold_value)
        return filtered_series

    def filter_dataframe(self, frame: polars.DataFrame) -> polars.DataFrame:
        if not self._observation_key and not self._prediction_key:
            return frame

        if isinstance(self._threshold_value, polars.Series):
            threshold_name = self._threshold_value.name
        else:
            threshold_name = 'threshold_value'

        joined_data = frame.with_columns(**{threshold_name: self._threshold_value})

        if self._observation_key and isinstance(self._observation_key, str):
            observation_key = self._observation_key
        elif self._observation_key:
            observation_key = self._observation_key.name
        else:
            observation_key = None

        if observation_key:
            keep_or_drop_observation = self._operator(joined_data[observation_key], joined_data[threshold_name])
        else:
            keep_or_drop_observation = True

        if self._prediction_key and isinstance(self._prediction_key, str):
            prediction_key = self._prediction_key
        elif self._prediction_key:
            prediction_key = self._prediction_key.name
        else:
            prediction_key = None

        if prediction_key:
            keep_or_drop_prediction = self._operator(joined_data[prediction_key], joined_data[threshold_name])
        else:
            keep_or_drop_prediction = True

        keep_or_drop = keep_or_drop_observation & keep_or_drop_prediction

        filtered_frame = joined_data[keep_or_drop]
        return filtered_frame

    def __call__(self, frame: PolarsData, *args, **kwargs) -> PolarsData:
        if isinstance(frame, polars.Series):
            filtered_data = self.filter_series(frame)
        else:
            filtered_data = self.filter_dataframe(frame)

        return filtered_data


class ThresholdMetadata:
    """
    Holds the bare minimum data about thresholds used to filter and interpret data
    """
    @classmethod
    def all(cls, weight: NUMBER):
        """
        Indicate that all values are to be used

        Args:
            weight: The significance of the threshold

        Returns:
            A new threshold definition stating that all values should be considered and that nothing should
                be filtered out
        """
        return cls(name="All", weight=weight, operator=None)

    def __init__(self, name: str, weight: NUMBER, operator: typing.Optional[NUMERIC_FILTER] = ge):
        self.__name = name
        self.__weight = weight
        self.__operator = operator

    @property
    def name(self):
        """
        The name of the threshold
        """
        return self.__name

    @property
    def weight(self) -> NUMBER:
        """
        The significance of the threshold
        """
        return self.__weight

    @property
    def operator(self) -> typing.Optional[NUMERIC_FILTER]:
        """
        How the threshold is applied
        """
        return self.__operator

    @property
    def allow_all(self) -> bool:
        """
        Whether to actually apply the threshold. The default 'All' threshold is essentially a no-op.
        """
        return self.__operator is None

    def __str__(self):
        return (
            f"{self.name.replace('_', ' ').title()}: "
            f"{self.operator.__qualname__ if self.__operator is not None else 'Allow All'} = {self.weight}"
        )

    def __repr__(self):
        return str(self)

    def __hash__(self):
        return hash((self.__name, self.__weight, self.__operator))

    def __eq__(self, other):
        if not isinstance(other, ThresholdMetadata):
            raise TypeError(f"Cannot compare a {self.__class__.__qualname__} to a {other.__class__.__name__}")
        return hash(self) == hash(other)

    def __gt__(self, other):
        if not isinstance(other, ThresholdMetadata):
            raise TypeError(f"Cannot compare a {self.__class__.__qualname__} to a {other.__class__.__name__}")

        if self.name > other.name or self.name == other.name and self.weight > other.weight:
            return True

        if self.name == other.name and self.weight > other.weight:
            return True

        if self.name == other.name and self.weight == other.weight and str(self.operator.__qualname__) > str(other.operator.__qualname__):
            return True

        return False

    def __lt__(self, other):
        if not isinstance(other, ThresholdMetadata):
            raise TypeError(f"Cannot compare a {self.__class__.__qualname__} to a {other.__class__.__name__}")

        if self.name < other.name or self.name == other.name and self.weight < other.weight:
            return True

        if self.name == other.name and self.weight < other.weight:
            return True

        if self.name == other.name and self.weight == other.weight and str(self.operator.__qualname__) < str(other.operator.__qualname__):
            return True

        return False

    def __ge__(self, other):
        return self == other or self > other

    def __le__(self, other):
        return self == other or self < other


class Threshold(ThresholdMetadata, FRAME_FILTER):
    @staticmethod
    def default() -> "Threshold":
        return Threshold(name="All", value=-infinity, weight=1, on_observed=False, on_predicted=False)

    def __init__(
        self,
        name: str,
        value: NUMBER,
        weight: NUMBER,
        on_observed: bool = True,
        on_predicted: bool = False,
        observed_value_key: str = None,
        predicted_value_key: str = None,
        operator: NUMERIC_FILTER = None
    ):
        """

        Args:
            name: The name of the threshold
            value:
            weight:
            on_observed:
            on_predicted:
            observed_value_key:
            predicted_value_key:
            operator:
        """
        data_is_existent = value is not None

        if data_is_existent and isinstance(value, (polars.DataFrame, polars.Series)):
            data_is_existent = len(value) != 0
        elif data_is_existent:
            data_is_existent &= not numpy.isnan(value)

        if not data_is_existent and None in (name, weight) or numpy.isnan(weight) or not name:
            raise ValueError(
                    f"Thresholds must have a name, a value, and a weight. "
                    f"Received: name='{name}', value='{value}, and weight='{weight}'"
            )

        if on_observed and not observed_value_key:
            raise ValueError(
                    f"The name of the observed column must be given if the threshold named '{name}' "
                    f"is going to be applied to the observed values"
            )

        if on_predicted and not predicted_value_key:
            raise ValueError(
                    f"The name of the predicted column must be given if the threshold named '{name}' "
                    f"is going to be applied to the predicted values"
            )

        super().__init__(name=name, weight=weight, operator=operator)
        self._value = value
        self._on_predicted = on_predicted
        self._on_observed = on_observed
        self._observed_value_key = observed_value_key
        self._predicted_value_key = predicted_value_key
        self._allow = self._build_filter(value, operator)

    def _build_filter(self, threshold_value: NUMBER, operator: NUMERIC_FILTER = None) -> FRAME_FILTER:
        if operator is None:
            operator = Operators.greater_than_or_equal

        filter_func = ValueFilter(
            operator=operator,
            threshold_value=threshold_value,
            observation_key=self._observed_value_key if self._on_observed else None,
            prediction_key=self._predicted_value_key if self._on_predicted else None
        )
        return filter_func

    def __call__(self, pairs: PolarsData) -> PolarsData:
        return self._allow(pairs)

    @property
    def value(self) -> NUMBER:
        return self._value

    def __str__(self) -> str:
        return f"{self.name}"

    def __repr__(self) -> str:
        return f"Threshold(name={self.name}, value={self.value}, weight={self.weight})"
