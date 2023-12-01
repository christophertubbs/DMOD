"""
Defines a series of classes that may be used to represent a date that may have a full ISO 8601 duration
added or subtracted from it
"""
from __future__ import annotations

import typing
import calendar

from datetime import datetime
from datetime import timedelta

from dateutil.parser import parse as parse_date

import numpy
import pandas

from .duration import RelativeDuration
from .string import CaseInsensitiveString

from .group import FiniteGroup
from .group import GroupMember


def _is_integer(value) -> bool:
    return numpy.issubdtype(type(value), numpy.integer)


class Month:
    def __init__(
        self,
        number: int,
        *,
        on_rollover: typing.Union[typing.Callable, typing.Iterable[typing.Callable]] = None,
        on_rollback: typing.Union[typing.Callable, typing.Iterable[typing.Callable]] = None
    ):
        if number <= 0 or number > 12:
            raise ValueError(f"The only valid month numbers are [1, 12] but received {number}")

        self.__name = CaseInsensitiveString(calendar.month_name[number])
        self.__abbreviation = CaseInsensitiveString(calendar.month_abbr[number])
        self.__month_number = number
        self.__leap_year = FiniteGroup(self.__name, range(1, calendar.monthrange(2020, number)[1] + 1))
        self.__normal_year = FiniteGroup(self.__name, range(1, calendar.monthrange(2021, number)[1] + 1))

        if on_rollover is None:
            on_rollover = []
        elif isinstance(on_rollover, typing.Callable):
            on_rollover = [on_rollover]
        else:
            on_rollover = [handler for handler in on_rollover]

        self.__on_rollover = on_rollover

        if on_rollback is None:
            on_rollback = []
        elif isinstance(on_rollback, typing.Callable):
            on_rollback = [on_rollback]
        else:
            on_rollback = [handler for handler in on_rollback]

        self.__on_rollback: typing.List[typing.Callable] = on_rollback

    @property
    def leap_year(self) -> FiniteGroup[int]:
        return self.__leap_year

    @property
    def normal_year(self) -> FiniteGroup[int]:
        return self.__normal_year

    @property
    def abbreviation(self) -> str:
        return self.__abbreviation

    @property
    def name(self) -> str:
        return self.__name

    @property
    def number(self) -> int:
        return self.__month_number

    def __call__(self, year: int) -> FiniteGroup[int]:
        if year % 4 == 0:
            return self.__leap_year
        return self.__normal_year

    def __str__(self):
        return self.__name

    def __repr__(self):
        return f"{self.__abbreviation}: Leap Year: {str(self.__leap_year)}, Normal Year: {str(self.__normal_year)}"


class MonthsOfYear(typing.Mapping[str, Month]):
    def __getitem__(self, index: typing.Union[str, int]) -> Month:
        if _is_integer(index):
            return self.__month_groups.raw_value(index)

        if index in self.__months:
            return self.__months[index]

        raise ValueError(f"{index} is not a valid index for the Months of the Year")

    def __len__(self) -> int:
        return len(self.__month_groups)

    def __iter__(self) -> typing.Iterator[Month]:
        return iter([month.value for month in self.__month_groups])

    def __init__(self):
        self.__month_groups = FiniteGroup(
            "Months",
            [
                Month(number)
                for number in range(1, 13)
            ]
        )
        self.__months: typing.Dict[str, Month] = {}

        for member in self.__month_groups:
            self.__months[member.value.abbreviation] = member.value
            self.__months[member.value.name] = member.value


class Year:
    def __init__(self, year: int):
        self.__year = year
        self.__months = {}
        self.__month_names = [None]
        self.__update_months()

    def __update_months(self):
        self.__months = {}
        self.__month_names = [None]

        for month in Months:
            self.__months[month.name] = month(self.year)
            self.__months[month.abbreviation] = month(self.year)
            self.__month_names.append(month.name)

    @property
    def year(self):
        return self.__year

    @year.setter
    def year(self, new_year: int):
        if not _is_integer(new_year):
            raise TypeError(f"Years may only be represented by integers. Received '{new_year}: {type(new_year)}'")

        self.__year = new_year
        self.__update_months()

    def increment(self, amount: int = None):
        self.__year += amount if amount is not None else 1
        self.__update_months()

    def decrement(self, amount: int = None):
        self.__year -= amount if amount is not None else 1
        self.__update_months()

    def get_month_by_number(self, month_number: int) -> FiniteGroup[int]:
        if _is_integer(month_number):
            if 0 < month_number <= 12:
                return self.__months[self.__month_names[month_number]]
            else:
                raise KeyError(
                    f"Numerical indices for the months of a year are only valid between [1, 12]. Received {month_number}"
                )
        else:
            raise TypeError(
                f"`get_month_by_number` only accepts integer month numbers for month retrieval. "
                f"Received '{month_number}: {type(month_number)}'"
            )

    @property
    def is_leap_year(self) -> bool:
        return self.__year % 4 == 0

    def __getitem__(self, index: typing.Union[int, str]) -> FiniteGroup[int]:
        if _is_integer(index):
            return self.get_month_by_number(index)

        if index in self.__months:
            return self.__months[index]

        raise ValueError(f"'{index}: {type(index)}' is not a valid index for the Months in a Year")

    def __len__(self) -> int:
        return sum([
            len(self.__months[month_name])
            for month_name in self.__month_names
        ])

    def __iter__(self) -> typing.Iterator[FiniteGroup[int]]:
        return iter([self.__months[month_name] for month_name in self.__month_names])

    def __str__(self):
        return str(self.__year)

    def __repr__(self):
        return self.__str__()


Months = MonthsOfYear()
Hours = FiniteGroup("Hours", [value for value in range(24)])
Minutes = FiniteGroup("Minutes", [value for value in range(60)])
Seconds = FiniteGroup("Seconds", [value for value in range(60)])


class ClockworkDate:
    @classmethod
    def from_datetime(cls, dt: datetime) -> ClockworkDate:
        return cls(
            year=dt.year,
            month=dt.month,
            day=dt.day,
            hour=dt.hour,
            minute=dt.minute,
            second=dt.second
        )

    @classmethod
    def from_timestamp(cls, timestamp: pandas.Timestamp) -> ClockworkDate:
        return cls(
            year=timestamp.year,
            month=timestamp.month,
            day=timestamp.day,
            hour=timestamp.hour,
            minute=timestamp.minute,
            second=timestamp.second
        )

    @classmethod
    def from_string(cls, date_string: str) -> ClockworkDate:
        date_and_time = parse_date(date_string)
        return cls.from_datetime(date_and_time)

    def __init__(
        self,
        year: int,
        month: typing.Union[str, int] = None,
        day: int = None,
        hour: int = None,
        minute: int = None,
        second: int = None
    ):
        if _is_integer(month):
            years_from_months, month = divmod(month, 12)
            year += years_from_months

        self.__current_year: Year = Year(year)
        self.__current_month: Month = Months[month if month is not None else 1]

        if _is_integer(second):
            adjustment_seconds, second = divmod(second, 60)
        else:
            adjustment_seconds = 0

        if _is_integer(minute):
            adjustment_minutes, minute = divmod(minute, 60)
        else:
            adjustment_minutes = 0

        if _is_integer(hour):
            adjustment_hours, hour = divmod(hour, 24)
        else:
            adjustment_hours = 0

        if _is_integer(day) and day > self.__current_month(self.year).max:
            adjustment_days = day - self.__current_month(self.year).max
            day = self.__current_month(self.year).max
        else:
            adjustment_days = 0

        self.__current_day: GroupMember[int] = self.__current_month(year)(
            value=day,
            on_rollover=self.__day_rolled_over,
            on_rollback=self.__day_rolled_back
        )

        self.__current_hour: GroupMember[int] = Hours(
            value=hour,
            on_rollover=self.__hour_rolled_over,
            on_rollback=self.__hour_rolled_back
        )

        self.__current_minute: GroupMember[int] = Minutes(
            value=minute,
            on_rollover=self.__minute_rolled_over,
            on_rollback=self.__minute_rolled_back
        )

        self.__current_second: GroupMember[int] = Seconds(
            value=second,
            on_rollover=self.__second_rolled_over,
            on_rollback=self.__second_rolled_back
        )

        if adjustment_seconds is not None and adjustment_seconds != 0:
            if adjustment_seconds > 0:
                self.__current_second.increment(adjustment_seconds)
            else:
                self.__current_second.decrement(abs(adjustment_seconds))

        if adjustment_minutes is not None and adjustment_minutes != 0:
            if adjustment_minutes > 0:
                self.__current_minute.increment(adjustment_minutes)
            else:
                self.__current_minute.decrement(abs(adjustment_minutes))

        if adjustment_hours is not None and adjustment_hours != 0:
            if adjustment_hours > 0:
                self.__current_hour.increment(adjustment_hours)
            else:
                self.__current_hour.decrement(abs(adjustment_hours))

        if adjustment_days is not None and adjustment_days != 0:
            if adjustment_days > 0:
                self.__current_day.increment(adjustment_days)
            else:
                self.__current_day.decrement(abs(adjustment_days))

    def __second_rolled_over(self, *args, **kwargs):
        self.__current_minute.increment()

    def __minute_rolled_over(self, *args, **kwargs):
        self.__current_hour.increment()

    def __hour_rolled_over(self, *args, **kwargs):
        self.__current_day.increment()

    def __day_rolled_over(self, *args, **kwargs):
        self.__increment_month()

    def __month_rolled_over(self, *args, **kwargs):
        self.__current_year.increment()

    def __year_rolled_back(self, *args, **kwargs):
        self.__current_year.decrement()

    def __month_rolled_back(self, *args, **kwargs):
        self.__current_year.decrement()

    def __day_rolled_back(self, *args, **kwargs):
        self.__decrement_month()

    def __hour_rolled_back(self, hour: GroupMember[int]):
        self.__current_day.decrement()

    def __minute_rolled_back(self, minute: GroupMember[int]):
        pass

    def __second_rolled_back(self, minute: GroupMember[int]):
        pass

    def __update_month(self, index: typing.Union[int, str]):
        new_month = Months[index]
        days_in_month = new_month(self.year)

        if self.day == self.__current_month(self.year).max and self.day > days_in_month.max:
            use_final_day = True
        else:
            use_final_day = False

        self.__current_month = new_month
        self.__current_day.switch_group(
            new_group=days_in_month,
            new_index=days_in_month.final_index if use_final_day else None
        )

    def __increment_month(self, amount: int = 0):
        if amount is None:
            amount = 1

        while amount > 0:
            next_index = self.month + 1

            if next_index > 12:
                self.__update_month(next_index)

            amount -= 1

    def __decrement_month(self, amount: int = 0):
        if amount is None:
            amount = 1

        while amount > 0:
            next_index = self.month - 1

            if next_index < 1:
                self.__update_month(next_index)

            amount -= 1

    @property
    def year(self):
        return self.__current_year.year

    @property
    def month(self):
        return self.__current_month.number

    @property
    def month_name(self) -> str:
        return self.__current_month.name

    @property
    def day(self) -> int:
        return self.__current_day.value

    @property
    def hour(self) -> int:
        return self.__current_hour.value

    @property
    def minute(self) -> int:
        return self.__current_minute.value

    @property
    def second(self) -> int:
        return self.__current_second.value

    def __add_timedelta(self, delta: timedelta) -> ClockworkDate:
        minutes, seconds = divmod(delta.total_seconds(), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        self.__current_second.increment(seconds)
        self.__current_minute.increment(minutes)
        self.__current_hour.increment(hours)
        self.__current_day.increment(days)
        return self

    def __add_relative_duration(self, duration: RelativeDuration) -> ClockworkDate:
        self.__current_second.increment(duration.seconds)
        self.__current_minute.increment(duration.minutes)
        self.__current_hour.increment(duration.hours)
        self.__current_day.increment(duration.days)
        self.__increment_month(duration.months)
        self.__current_year.increment(duration.years)
        return self

    def __subtract_timedelta(self, delta: timedelta) -> ClockworkDate:
        minutes, seconds = divmod(delta.total_seconds(), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        self.__current_second.decrement(seconds)
        self.__current_minute.decrement(minutes)
        self.__current_hour.decrement(hours)
        self.__current_day.decrement(days)
        return self

    def __subtract_relative_duration(self, duration: RelativeDuration) -> ClockworkDate:
        self.__current_second.decrement(duration.seconds)
        self.__current_minute.decrement(duration.minutes)
        self.__current_hour.decrement(duration.hours)
        self.__current_day.decrement(duration.days)
        self.__decrement_month(duration.months)
        self.__current_year.decrement(duration.years)
        return self

    def to_timestamp(self) -> pandas.Timestamp:
        return pandas.Timestamp(
            year=self.__current_year.year,
            month=self.__current_month.number,
            day=self.__current_day.value,
            hour=self.__current_hour.value,
            minute=self.__current_minute.value,
            second=self.__current_second.value
        )

    def to_datetime(self) -> datetime:
        return datetime(
            year=self.__current_year.year,
            month=self.__current_month.number,
            day=self.__current_day.value,
            hour=self.__current_hour.value,
            minute=self.__current_minute.value,
            second=self.__current_second.value
        )

    def __add__(self, other: typing.Union[RelativeDuration, timedelta]) -> ClockworkDate:
        if isinstance(other, RelativeDuration):
            return self.__class__(
                year=self.year + other.years,
                month=self.month + other.months,
                day=self.day + other.days,
                minute=self.minute + other.minutes,
                second=self.second + other.seconds
            )
        elif isinstance(other, timedelta):
            minutes, seconds = divmod(other.total_seconds(), 60)
            hours, minutes = divmod(minutes, 60)
            days, hours = divmod(hours, 24)

            return self.__class__(
                year=self.year,
                month=self.month,
                day=self.day + days,
                hour=self.hour + hours,
                minute=self.minute + minutes,
                second=self.second + seconds
            )

        raise TypeError(
            f"May only add a RelativeDuration or timedelta to a {self.__class__.__name__}. "
            f"Received '{other}: {type(other)}'"
        )

    def __sub__(self, other: typing.Union[RelativeDuration, timedelta]) -> ClockworkDate:
        if isinstance(other, RelativeDuration):
            return self.__class__(
                year=self.year,
                month=self.month - other.total_months,
                day=self.day,
                minute=self.minute,
                second=self.second - other.total_seconds
            )
        elif isinstance(other, timedelta):
            seconds = abs(other.total_seconds())
            minutes, seconds = divmod(seconds, 60)
            hours, minutes = divmod(minutes, 60)
            days, hours = divmod(hours, 24)

            return self.__class__(
                year=self.year,
                month=self.month,
                day=self.day - days,
                hour=self.hour - hours,
                minute=self.minute - minutes,
                second=self.second - seconds
            )

        raise TypeError(
            f"May only add a RelativeDuration or timedelta to a {self.__class__.__name__}. "
            f"Received '{other}: {type(other)}'"
        )

    def __iadd__(self, other: typing.Union[RelativeDuration, timedelta]) -> ClockworkDate:
        if isinstance(other, RelativeDuration):
            return self.__add_relative_duration(other)
        elif isinstance(other, timedelta):
            return self.__add_timedelta(other)

        raise TypeError(
            f"May only add a RelativeDuration or timedelta to a {self.__class__.__name__}. "
            f"Received '{other}: {type(other)}'"
        )

    def __isub__(self, other: typing.Union[RelativeDuration, timedelta]) -> ClockworkDate:
        if isinstance(other, RelativeDuration):
            return self.__subtract_relative_duration(other)
        elif isinstance(other, timedelta):
            return self.__subtract_timedelta(other)

        raise TypeError(
            f"May only add a RelativeDuration or timedelta to a {self.__class__.__name__}. "
            f"Received '{other}: {type(other)}'"
        )

    def __eq__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp]) -> bool:
        return self.year == other.year \
            and self.month == other.month \
            and self.day == other.day \
            and self.hour == other.hour \
            and self.minute == other.minute \
            and self.second == other.second

    def __ne__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp]) -> bool:
        return self.year != other.year \
            or self.month != other.month \
            or self.day != other.day \
            or self.hour != other.hour \
            or self.minute != other.minute \
            or self.second != other.second

    def __lt__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp]) -> bool:
        if self.year < other.year:
            return True
        elif self.year > other.year:
            return False

        # The years are equal at this point
        if self.month < other.month:
            return True
        elif self.month > other.month:
            return False

        # The months are equal at this point
        if self.day < other.day:
            return True
        elif self.day > other.day:
            return False

        # The days are equal at this point
        if self.hour < other.hour:
            return True
        elif self.hour > other.hour:
            return False

        # The hours are equal at this point
        if self.minute < other.minute:
            return True
        elif self.minute > other.minute:
            return False

        # The minutes are equal at this point
        return self.second < other.second

    def __le__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp]) -> bool:
        if self.year < other.year:
            return True
        elif self.year > other.year:
            return False

        # The years are equal at this point
        if self.month < other.month:
            return True
        elif self.month > other.month:
            return False

        # The months are equal at this point
        if self.day < other.day:
            return True
        elif self.day > other.day:
            return False

        # The days are equal at this point
        if self.hour < other.hour:
            return True
        elif self.hour > other.hour:
            return False

        # The hours are equal at this point
        if self.minute < other.minute:
            return True
        elif self.minute > other.minute:
            return False

        # The minutes are equal at this point
        return self.second <= other.second

    def __gt__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp]) -> bool:
        if self.year > other.year:
            return True
        elif self.year < other.year:
            return False

        # The years are equal at this point
        if self.month > other.month:
            return True
        elif self.month < other.month:
            return False

        # The months are equal at this point
        if self.day > other.day:
            return True
        elif self.day < other.day:
            return False

        # The days are equal at this point
        if self.hour > other.hour:
            return True
        elif self.hour < other.hour:
            return False

        # The hours are equal at this point
        if self.minute > other.minute:
            return True
        elif self.minute < other.minute:
            return False

        # The minutes are equal at this point
        return self.second > other.second

    def __ge__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp]) -> bool:
        if self.year > other.year:
            return True
        elif self.year < other.year:
            return False

        # The years are equal at this point
        if self.month > other.month:
            return True
        elif self.month < other.month:
            return False

        # The months are equal at this point
        if self.day > other.day:
            return True
        elif self.day < other.day:
            return False

        # The days are equal at this point
        if self.hour > other.hour:
            return True
        elif self.hour < other.hour:
            return False

        # The hours are equal at this point
        if self.minute > other.minute:
            return True
        elif self.minute < other.minute:
            return False

        # The minutes are equal at this point
        return self.second >= other.second