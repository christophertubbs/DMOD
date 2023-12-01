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
    @classmethod
    def from_string(cls, period: str) -> RelativeDuration:
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
        seconds = period.total_seconds()
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

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
        if self.__years != math.floor(self.__years):
            self.__months += (self.__years - math.floor(self.__years)) * 12
            self.__years = math.floor(self.__years)

        partial_hours = 0
        if self.__days != math.floor(self.__days):
            self.__hours += (self.__days - math.floor(self.__days)) * 24
            self.__days = math.floor(self.__days)

        partial_minutes = 0
        if self.__hours != math.floor(self.__hours):
            self.__minutes += (self.__hours - math.floor(self.__hours)) * 60
            self.__hours = math.floor(self.__hours)

        if self.__minutes != math.floor(self.__minutes):
            self.__seconds += (self.__minutes - math.floor(self.__minutes)) * 60
            self.__minutes = math.floor(self.__minutes)

        self.__seconds = round(self.__seconds)

        minutes_from_seconds = self.__seconds // 60
        leftover_seconds = self.__seconds - (minutes_from_seconds * 60)

        self.__seconds = leftover_seconds
        self.__minutes += minutes_from_seconds

        hours_from_minutes = self.__minutes // 60
        leftover_minutes = self.__minutes - (hours_from_minutes * 60)

        self.__minutes = leftover_minutes
        self.__hours += hours_from_minutes

        days_from_hours = self.__hours // 24
        leftover_hours = self.__hours - (days_from_hours * 24)

        self.__hours = leftover_hours
        self.__days += days_from_hours

        years_from_months = self.__months // 12
        leftover_months = self.__months - (years_from_months * 12)

        self.__months = leftover_months
        self.__years += years_from_months

    @property
    def years(self) -> int:
        return self.__years

    @property
    def months(self) -> int:
        return self.__months

    @property
    def days(self) -> int:
        return self.__days

    @property
    def hours(self) -> int:
        return self.__hours

    @property
    def minutes(self) -> int:
        return self.__minutes

    @property
    def seconds(self) -> int:
        return self.__seconds

    @property
    def total_months(self) -> int:
        return self.months + (self.years * 12)

    @property
    def total_seconds(self) -> int:
        seconds_in_minutes = 60
        seconds_in_hours = 60 * seconds_in_minutes
        seconds_in_days = 24 * seconds_in_hours

        return (self.days * seconds_in_days) \
            + (self.hours * seconds_in_hours) \
            + (self.minutes * seconds_in_minutes) \
            + self.seconds

    def add_year(self, quantity: typing.Union[int, float] = None) -> RelativeDuration:
        if quantity is None:
            quantity = 1

        self.__years += quantity
        self.__normalize()

        return self

    def add_month(self, quantity: typing.Union[int, float] = None) -> RelativeDuration:
        if quantity is None:
            quantity = 1

        self.__months += quantity
        self.__normalize()

        return self

    def add_day(self, quantity: typing.Union[int, float] = None) -> RelativeDuration:
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

    def __eq__(self, other: typing.Union[RelativeDuration, timedelta]) -> bool:
        other = self.__other_is_comparable(other)

        return self.total_months == other.total_months and self.total_seconds == other.total_seconds

    def __ne__(self, other: typing.Union[RelativeDuration, timedelta]) -> bool:
        other = self.__other_is_comparable(other)

        return self.total_months != other.total_months or self.total_seconds != other.total_seconds

    def __gt__(self, other: typing.Union[RelativeDuration, timedelta]) -> bool:
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

    def __lt__(self, other: typing.Union[RelativeDuration, timedelta]) -> bool:
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

    def __truediv__(self, other: typing.Union[int, float]) -> RelativeDuration:
        if not isinstance(other, (int, float)):
            raise TypeError(
                f"Cannot multiple duration - durations may only be divided by an int or float "
                f"but received '{other}: {type(other)}'"
            )

        if other == 0:
            raise ZeroDivisionError(
                f"A RelativeDuration cannot be divided by 0"
            )

        return self.__class__(
            years=self.years / other,
            months=self.months / other,
            days=self.days / other,
            hours=self.hours / other,
            minutes=self.minutes / other,
            seconds=self.seconds / other
        )