"""
Contains a class representing a full implementation of the ISO 8601 Duration format
"""
from __future__ import annotations

import json
import re
import typing
from datetime import timedelta

import math
import numpy
from typing_extensions import Self

DURATION_PATTERN = re.compile(
    r"(?<=P)"
    r"(?P<years>\d+(?=Y))?Y?"
    r"(?P<months>\d+(?=M))?M?"
    r"(?P<days>\d+(?=D))?D?"
    r"T?"
    r"(?P<hours>\d+(?=H))?H?"
    r"(?P<minutes>\d+(?=M))?M?"
    r"(?P<seconds>\d+(\.\d+)?(?=S))?"
)


class RelativeDuration:
    """
    A datetime duration that supports all parts of the ISO 8601 datetime format.

    The vanilla timedelta does not support durations of months
    """
    @classmethod
    def from_string(cls, period: str) -> RelativeDuration:
        """
        Convert an ISO 8601 duration string to a duration

        Details on the format may be found at https://en.wikipedia.org/wiki/ISO_8601#Durations

        The general pattern is "P#Y#M#DT#H#M#S"

        Examples:
            >>> repr(RelativeDuration.from_string("PT1H"))
            {"hours": 1}
            >>> repr(RelativeDuration.from_string("P1YT3H4S"))
            {"years": 1, "hours": 3, "seconds": 4}

        Args:
            period: The string to convert

        Returns:
            A new RelativeDuration object
        """
        duration_match = DURATION_PATTERN.search(period)
        years = int(float(duration_match.group("years") or "0"))
        months = int(float(duration_match.group("months") or "0"))
        days = int(float(duration_match.group("days") or "0"))
        hours = int(float(duration_match.group("hours") or "0"))
        minutes = int(float(duration_match.group("minutes") or "0"))
        seconds = int(float(duration_match.group("seconds") or "0"))

        return cls(
            years=years,
            months=months,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds
        )

    @classmethod
    def from_delta(cls, period: timedelta) -> RelativeDuration:
        """
        Convert a vanilla python timedelta into a RelativeDuration

        Args:
            period: The timedelta object to convert into a RelativeDuration

        Returns:
            A new RelativeDuration
        """
        # Normalize the values as much as possible by converting from pure seconds to days, hours, minutes, and seconds
        seconds = period.total_seconds()
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        # Months and years aren't indicated here since vanilla timedeltas don't support them
        return cls(
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds
        )

    def __init__(
        self,
        years: int = None,
        months: int = None,
        days: int = None,
        hours: int = None,
        minutes: int = None,
        seconds: typing.Union[int, float] = None
    ):
        """
        Constructor

        Args:
            years: The number of years forward or backward represented by this duration
            months: The number of months forward or backward represented by this duration
            days: The number of days forward or backward represented by this duration
            hours: The number of hours forward or backward represented by this duration
            minutes: The number of minutes forward or backward represented by this duration
            seconds: The number of seconds forward or backward represented by this duration
        """
        if years is not None and not numpy.issubdtype(type(years), numpy.integer):
            raise TypeError(
                f"The number of years in a RelativeDuration must be an int - received a `{type(years)}` instead"
            )

        if months is not None and not numpy.issubdtype(type(months), numpy.integer):
            raise TypeError(
                f"The number of months in a RelativeDuration must be an int - received a `{type(months)}` instead"
            )

        if days is not None and not numpy.issubdtype(type(days), numpy.integer):
            raise TypeError(
                f"The number of days in a RelativeDuration must be an int - received a `{type(days)}` instead"
            )

        if minutes is not None and not numpy.issubdtype(type(minutes), numpy.integer):
            raise TypeError(
                f"The number of minutes in a RelativeDuration must be an int - received a `{type(minutes)}` instead"
            )

        seconds_is_the_wrong_type = seconds is not None and not (
                numpy.issubdtype(type(seconds), numpy.integer)
                or numpy.issubdtype(type(seconds), numpy.floating)
        )

        if seconds_is_the_wrong_type:
            raise TypeError(
                f"The number of seconds in a RelativeDuration must be a float or an int - "
                f"received a `{type(minutes)}` instead"
            )

        self.__years = years or 0
        self.__months = months or 0
        self.__days = days or 0
        self.__hours = hours or 0
        self.__minutes = minutes or 0
        self.__seconds = seconds or 0

        self.__normalize()

    def __normalize(self):
        """
        Convert values that exceed ranges to the smallest possible quantity of units

        This will transform state like 23 Months, 28 Days, 96 Hours, 72 Minutes, 120 Seconds

        to

        1 Year, 11 Months, 32 Days, 1 Hours, 14 Minutes, 0 Seconds

        Days can't overflow into Months since the number of days in a month is variable
        """
        # If the years isn't a whole number, try to move as many months out of it as possible
        # Say we have `3.8` years. This will add `9.6` months and leave `3` years
        if self.__years != math.floor(self.__years):
            self.__months += (self.__years - math.floor(self.__years)) * 12
            self.__years = math.floor(self.__years)

        # If the days isn't a whole number, try to move as many hours out of it as possible
        # Say that the number of days is `3.29`. This will add `6.96` hours and leave the days at `3`
        if self.__days != math.floor(self.__days):
            self.__hours += (self.__days - math.floor(self.__days)) * 24
            self.__days = math.floor(self.__days)

        # If the number of hours isn't a whole number, try to move as many minutes out of it as possible
        # Say that the number of hours is `1.73`. This will add `43.8` minutes and leave the number of hours at `1`
        if self.__hours != math.floor(self.__hours):
            self.__minutes += (self.__hours - math.floor(self.__hours)) * 60
            self.__hours = math.floor(self.__hours)

        # If the number of minutes isn't a whole number, try to move as many seconds out of it as possible
        # Say that the number of minutes is `2.5`. This will add `30` to the seconds and leave the minutes at `2`
        if self.__minutes != math.floor(self.__minutes):
            self.__seconds += (self.__minutes - math.floor(self.__minutes)) * 60
            self.__minutes = math.floor(self.__minutes)

        self.__seconds = round(self.__seconds)

        minutes_from_seconds, leftover_seconds = divmod(self.__seconds, 60)

        self.__seconds = leftover_seconds
        self.__minutes += minutes_from_seconds

        hours_from_minutes, leftover_minutes = divmod(self.__minutes, 60)

        self.__minutes = leftover_minutes
        self.__hours += hours_from_minutes

        days_from_hours, leftover_hours = divmod(self.__hours, 24)

        self.__hours = leftover_hours
        self.__days += days_from_hours

        years_from_months, leftover_months = divmod(self.__months, 12)

        self.__months = leftover_months
        self.__years += years_from_months

    @property
    def years(self) -> int:
        """
        The number of years to transform a date by
        """
        return self.__years

    @property
    def months(self) -> int:
        """
        The number of months to transform a date by
        """
        return self.__months

    @property
    def days(self) -> int:
        """
        The number of days to transform a date by
        """
        return self.__days

    @property
    def hours(self) -> int:
        """
        The number of hours to transform a date by
        """
        return self.__hours

    @property
    def minutes(self) -> int:
        """
        The number of minutes to transform a date by
        """
        return self.__minutes

    @property
    def seconds(self) -> int:
        """
        The number of seconds to transform a date by
        """
        return self.__seconds

    @property
    def total_months(self) -> int:
        """
        The total number of months (separate from days/hours/minutes/seconds) to transform a date by
        """
        return self.months + (self.years * 12)

    @property
    def total_seconds(self) -> int:
        """
        The total number of seconds (separate from years/months) to transform a date by
        """
        seconds_in_minutes = 60
        seconds_in_hours = 60 * seconds_in_minutes
        seconds_in_days = 24 * seconds_in_hours

        return (self.days * seconds_in_days) \
            + (self.hours * seconds_in_hours) \
            + (self.minutes * seconds_in_minutes) \
            + self.seconds

    def add_year(self, quantity: typing.Union[int, float] = None) -> Self:
        """
        Add a year to the duration

        Args:
            quantity: The amount of years to add. Default: 1

        Returns:
            The updated duration
        """
        if quantity is None:
            quantity = 1

        self.__years += quantity
        self.__normalize()

        return self

    def add_month(self, quantity: typing.Union[int, float] = None) -> Self:
        """
        Add a number of months to the duration

        Args:
            quantity: The number of months to add. Default: 1

        Returns:
            The updated duration
        """
        if quantity is None:
            quantity = 1

        self.__months += quantity
        self.__normalize()

        return self

    def add_day(self, quantity: typing.Union[int, float] = None) -> Self:
        if quantity is None:
            quantity = 1

        self.__days += quantity
        self.__normalize()

        return self

    def add_minute(self, quantity: typing.Union[int, float] = None) -> RelativeDuration:
        if quantity is None:
            quantity = 1

        self.__minutes += quantity
        self.__normalize()

        return self

    def add_second(self, quantity: typing.Union[int, float] = None) -> RelativeDuration:
        if quantity is None:
            quantity = 1

        self.__seconds += quantity
        self.__normalize()

        return self

    def __other_is_comparable(self, other: typing.Union[RelativeDuration, timedelta]) -> RelativeDuration:
        if not isinstance(other, (RelativeDuration, timedelta)):
            raise TypeError(f"Cannot compare a {self.__class__.__name__} object to a {type(other)} object")

        if isinstance(other, timedelta):
            other = self.__class__.from_delta(other)

        return other

    def __eq__(self, other: typing.Union[RelativeDuration, timedelta, str]) -> bool:
        if isinstance(other, str):
            other = RelativeDuration.from_string(other)

        other = self.__other_is_comparable(other)

        return self.total_months == other.total_months and self.total_seconds == other.total_seconds

    def __ne__(self, other: typing.Union[RelativeDuration, timedelta, str]) -> bool:
        if isinstance(other, str):
            other = RelativeDuration.from_string(other)

        other = self.__other_is_comparable(other)

        return self.total_months != other.total_months or self.total_seconds != other.total_seconds

    def __gt__(self, other: typing.Union[RelativeDuration, timedelta]) -> bool:
        if isinstance(other, str):
            other = RelativeDuration.from_string(other)

        other = self.__other_is_comparable(other)

        if self == other:
            return False

        months_matter = self.total_months != other.total_months
        seconds_matter = self.total_seconds != other.total_seconds

        if not months_matter and not seconds_matter:
            return False

        if months_matter and self.total_months < other.total_months:
            return False
        elif months_matter and self.total_months > other.total_months:
            return True
        elif seconds_matter and self.total_seconds <= other.total_seconds:
            return False

        return True

    def __ge__(self, other: typing.Union[RelativeDuration, timedelta]) -> bool:
        return not self < other

    def __lt__(self, other: typing.Union[RelativeDuration, timedelta, str]) -> bool:
        if isinstance(other, str):
            other = RelativeDuration.from_string(other)

        other = self.__other_is_comparable(other)

        if self == other:
            return False

        months_matter = self.total_months != other.total_months
        seconds_matter = self.total_seconds != other.total_seconds

        if months_matter and self.total_months < other.total_months:
            return True
        elif months_matter and self.total_months > other.total_months:
            return False
        elif seconds_matter and self.total_seconds > other.total_seconds:
            return False

        return True

    def __str__(self):
        if not self.total_months and not self.total_seconds:
            return "PT0S"

        representation = "P"

        if self.years:
            representation += f"{self.years}Y"

        if self.months:
            representation += f"{self.months}M"

        if self.days:
            representation += f"{self.days}"

        if self.hours or self.minutes or self.seconds:
            representation += "T"

        if self.hours:
            representation += f"{self.hours}H"

        if self.minutes:
            representation += f"{self.minutes}M"

        if self.seconds:
            representation += f"{self.seconds}S"

        return representation

    def dict(self) -> typing.Dict[str, int]:
        pieces = {}

        if self.years:
            pieces['years'] = self.years

        if self.months:
            pieces['months'] = self.months

        if self.days:
            pieces['days'] = self.days

        if self.hours:
            pieces['hours'] = self.hours

        if self.minutes:
            pieces['minutes'] = self.minutes

        if self.seconds:
            pieces['seconds'] = self.seconds

        return pieces

    def __repr__(self):
        return json.dumps(self.dict())

    def __le__(self, other: typing.Union[RelativeDuration, timedelta]) -> bool:
        return not self > other

    def __bool__(self) -> bool:
        return self.total_months != 0 or self.total_seconds != 0

    def __abs__(self) -> RelativeDuration:
        return RelativeDuration(
            years=abs(self.years),
            months=abs(self.months),
            days=abs(self.days),
            hours=abs(self.hours),
            minutes=abs(self.minutes),
            seconds=abs(self.seconds)
        )

    def __mul__(self, other: typing.Union[int, float]) -> RelativeDuration:
        if not isinstance(other, (int, float)):
            raise TypeError(
                f"Cannot multiple duration - durations may only be multiplied by an int or float "
                f"but received '{other}: {type(other)}'"
            )

        return self.__class__(
            years=self.years * other,
            months=self.months * other,
            days=self.days * other,
            hours=self.hours * other,
            minutes=self.minutes * other,
            seconds=self.seconds * other
        )

    def __truediv__(self, other) -> RelativeDuration:
        raise Exception("Relative Durations are not divisible")