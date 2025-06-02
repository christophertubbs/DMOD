"""
Defines a custom measurement unit registry that handles extra hydrological units
"""
from __future__ import annotations

import typing
import inspect

from collections import UserDict

import pint

_T = typing.TypeVar("_T")


class CaseInsensitiveDict(UserDict):
    def __init__(self, data=None, **kwargs):
        # Initialize with lowercased keys
        super().__init__()
        if data:
            self.update(data)
        if kwargs:
            self.update(kwargs)

    def __setitem__(self, key, value):
        # Store keys in lowercase form
        super().__setitem__(key.lower(), value)

    def __getitem__(self, key):
        # Access using lowercase keys
        return super().__getitem__(str(key).lower())

    def __delitem__(self, key):
        # Delete using lowercase keys
        super().__delitem__(key.lower())

    def __contains__(self, key):
        # Check existence using lowercase keys
        return super().__contains__(key.lower())

    def update(self, data=None, **kwargs):
        # Update the dictionary with lowercase keys
        if data:
            if isinstance(data, dict):
                for key, value in data.items():
                    self[key] = value
            else:  # if data is an iterable of key-value pairs
                for key, value in data:
                    self[key] = value
        for key, value in kwargs.items():
            self[key] = value


class UnitRegistry:
    """
    A wrapper for a pint registry that handles extra hydrological units
    """
    def __init__(self, synonyms: typing.Dict[str, str] = None):
        # `pint` cannot have '-' or '/' in definitions, so define those here
        self.__unsupported_to_supported_units = CaseInsensitiveDict({
            "m3 s-1": "m^3/s",
            "ft3 s-1": "ft^3/s",
            "m3/s": "m^3/s",
            "ft3/s": "ft^3/s",
            "acre-foot": "acre_foot",
            "acre-feet": "acre_feet",
            "ac-ft": "acre_foot",
        })

        if synonyms:
            self.__unsupported_to_supported_units.update(synonyms)

        self.__timed_units: typing.MutableMapping[str, bool] = CaseInsensitiveDict()
        self.__time_unit_for_unit: typing.MutableMapping[str, str] = CaseInsensitiveDict()

        self.__registry = pint.UnitRegistry()

        self.__registry.define("m3 = m^3")
        self.__registry.define("ft3 = ft^3")

        self.__registry.define("cfs = ft^3/s")
        self.__registry.define("CFS = ft^3/s")

        self.__registry.define("KCFS = 1000 * cfs")
        self.__registry.define("kcfs = 1000 * cfs")

        self.__registry.define("cms = m^3/s")
        self.__registry.define("CMS = m^3/s")

        self.__acknowledge_time_units()

    def __acknowledge_time_units(self):
        """
        Record which time-based units are time-based units and what they are measured in
        """
        def is_timed_unit(unit: pint.Unit) -> bool:
            if not isinstance(unit, pint.Unit):
                return False
            return '[time]' in unit.dimensionality

        timed_units: typing.Sequence[pint.Unit] = [
            unit
            for unit_name, unit in inspect.getmembers(self.registry, is_timed_unit)
        ]
        self.__timed_units.update({
            str(unit): True
            for unit in timed_units
        })

        for unit in timed_units:
            _, dimensions = self.get_quantity(1, unit).to_base_units().to_tuple()
            for dimension_name, _ in dimensions:
                if is_timed_unit(dimension_name):
                    self.__time_unit_for_unit[str(unit)] = dimension_name
                    break

    def is_timed(self, unit_name: str) -> bool:
        """
        Determines if the given unit has a time dimension

        Args:
            unit_name: The name of the unit to check

        Returns:
            True if the unit has a time dimension, False otherwise
        """
        if unit_name in self.__timed_units:
            return self.__timed_units[unit_name]

        _, unit = self.__registry.get_base_units(unit_name)
        return self.__timed_units.setdefault(unit_name, '[time]' in unit.dimensionality)

    def time_unit(self, unit_name: str) -> typing.Optional[str]:
        """
        Determines the unit of time attached to the given unit

        Given a unit such as 'cms', this should return 'second'. Given 'ft^3', this should return None.

        Args:
            unit_name: The name of the unit to check

        Returns:
            The name of the unit of time attached to the given unit if it is timed
        """
        unit_of_time = self.__time_unit_for_unit.get(unit_name)

        if unit_of_time is not None:
            return unit_of_time

        quantity: pint.Quantity = self.registry.Quantity(1, unit_name).to_base_units()
        _, dimensions = quantity.to_tuple()

        for dimension_name, _ in dimensions:
            if self.is_timed(dimension_name):
                return self.__time_unit_for_unit.setdefault(unit_name, dimension_name)

        return None

    def get_quantity(self, value: _T, value_type: str) -> pint.Quantity:
        """
        Converts a value into a specified Quantity object

        >>> example = _UnitRegistry()
        >>> quantity = example.get_quantity(5.48, 'ft3 s-1')
        >>> similar_quantity = example.registry.Quantity(5.48, 'ft3/s')
        >>> similar_quantity.magnitude == quantity.magnitude
        True
        >>> similar_quantity.units == quantity.units
        True
        >>> similar_quantity == quantity
        True
        >>> dissimilar_quantity = example.registry.Quantity(5.48, 'm3 s-1')
        >>> dissimilar_quantity.magnitude == quantity.magnitude
        False
        >>> dissimilar_quantity.units == quantity.units
        False
        >>> dissimilar_quantity == quantity
        False

        NOTE: Quantity objects may be used just like regular values, but with additional logic and functions.

        Args:
            value: The amount in the Quantity
            value_type: The unit of the Quantity

        Returns:

        """
        value_type = self.__unsupported_to_supported_units.get(value_type, value_type)

        return self.__registry.Quantity(value, value_type)

    @property
    def unsupported_to_supported_units(self) -> typing.Mapping[str, str]:
        """
        Creates a copy of the mapping from specialized unit descriptors `not` supported by pint to matching
        unit descriptors that ARE supported by pint

        The mapping just links unsupported synonyms, like "m3 s-1" => "m^3/s". "m3 s-1" may be considered an oddball,
        but it IS used by data sources that this library needs to support

        Returns:
            The mapping from specialized unit descriptors `not` supported by pint to matching unit descriptors
            that ARE supported by pint
        """
        return self.__unsupported_to_supported_units.copy()

    @property
    def registry(self) -> pint.registry.UnitRegistry:
        return self.__registry

units: UnitRegistry = UnitRegistry()