import typing
import numbers

import polars

_T = typing.TypeVar("_T")

from dmod.metrics.unit_registry import UnitRegistry


class UnitConverter(UnitRegistry):
    """
    A wrapper for a pint conversion registry containing common, yet abnormal units
    """

    def convert(self, value: _T, from_unit: str, to_unit: str) -> _T:
        """
        Converts the amount of the first unit to an amount of the second

        Args:
            value: The original amount of the original unit
            from_unit: The unit describing the original magnitude of the value
            to_unit: The unit to convert the original value into

        Returns:
            The converted amount
        """
        from_unit = self.__unsupported_to_supported_units.get(from_unit, from_unit)
        to_unit = self.__unsupported_to_supported_units.get(to_unit, to_unit)

        return self.__registry.convert(value, from_unit, to_unit)

    def convert_mapping(
        self,
        mapping: typing.Mapping[typing.Literal["value", "to_unit", "from_unit"], typing.Union[str,float]]
    ) -> float:
        return self.convert(**mapping)

    def convert_frame(
        self,
        frame: polars.DataFrame,
        value_column: str,
        from_unit: str,
        to_unit: str
    ) -> polars.DataFrame:
        """
        Converts values in one column in a dataframe from the given unit to the other given unit

        Args:
            frame:
            value_column:
            from_unit:
            to_unit:

        Returns:
            The updated dataframe with the column bearing the value having the same value in another unit
        """
        if from_unit in frame.columns:
            from_expression = polars.col(from_unit).alias("from_unit")
        else:
            from_expression = polars.lit(from_unit).alias("from_unit")

        if to_unit in frame.columns:
            to_expression = polars.col(to_unit).alias("to_unit")
        else:
            to_expression = polars.lit(to_unit).alias("to_unit")

        value_expression = polars.col(value_column).alias("value")

        return frame.with_columns([
            polars.struct(
                [value_expression, from_expression, to_expression]
            ).map_elements(
                self.convert_mapping,
                return_dtype=polars.Float32
            ).alias(value_column)
        ])


_COMMON_CONVERTER = UnitConverter()


def convert(value: numbers.Number, from_unit: str, to_unit: str):
    """
    Converts a number from one unit into another

    Args:
        value: The value to convert
        from_unit: The current unit of measurement
        to_unit: The desired unit of measurement

    Returns:
        A new number reflecting a change of measurement unit
    """
    return _COMMON_CONVERTER.convert(value, from_unit, to_unit)


def convert_frame(
    frame: polars.DataFrame,
    value_column: str,
    from_unit: str,
    to_unit: str
) -> polars.DataFrame:
    """
    Converts values in one column in a dataframe from the given unit to the other given unit

    Args:
        frame:
        value_column:
        from_unit:
        to_unit:

    Returns:
        The updated dataframe with the column bearing the value having the same value in another unit
    """
    return _COMMON_CONVERTER.convert_frame(frame, value_column, from_unit, to_unit)