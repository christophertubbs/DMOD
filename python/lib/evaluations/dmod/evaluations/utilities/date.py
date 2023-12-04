"""
Defines a series of classes that may be used to represent a date that may have a full ISO 8601 duration
added or subtracted from it
"""
from __future__ import annotations

import typing
import calendar

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from datetime import tzinfo

from dateutil.parser import parse as parse_date

import numpy
import pandas
from typing_extensions import Self

from .duration import RelativeDuration
from .string import CaseInsensitiveString

from .group import FiniteGroup
from .group import GroupMember


def _is_integer(value) -> bool:
    return numpy.issubdtype(type(value), numpy.integer)


def normalize_datetime(
    dt: typing.Union[ClockworkDate, datetime, pandas.Timestamp, str]
) -> typing.Union[ClockworkDate, datetime, pandas.Timestamp]:
    if isinstance(dt, str):
        dt = parse_date(dt)

    if isinstance(dt, ClockworkDate):
        return dt
    elif dt.tzinfo:
        dt = dt.astimezone(timezone.utc)

    return dt


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
        self.__leap_year: typing.Optional[FiniteGroup[int]] = None
        self.__normal_year: typing.Optional[FiniteGroup[int]] = None

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
        if self.__leap_year is None:
            self.__leap_year = FiniteGroup(self.__name, range(1, calendar.monthrange(2020, self.number)[1] + 1))
        return self.__leap_year

    @property
    def normal_year(self) -> FiniteGroup[int]:
        if self.__normal_year is None:
            self.__normal_year = FiniteGroup(self.__name, range(1, calendar.monthrange(2021, self.number)[1] + 1))
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
            return self.leap_year
        return self.normal_year

    def __str__(self):
        return self.__name

    def __repr__(self):
        return f"{self.__abbreviation}: Leap Year: {str(self.leap_year)}, Normal Year: {str(self.normal_year)}"


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
    """
    Represents a series of FiniteGroups daisy-chained together to form a date representation that may be incremented
    and decremented along a full ISO 8601 duration.

    Standard Python durations do not take months and years into account since the number of days in a month is
    variable. This is a date format that changes date and time parts by incrementing and decrementing rather
    than setting absolute values. When the values for the finite groups loop, the members they are chained to change
    as well. So, if a day rolls over, it will increment the month, then change the set of days for the month.
    This takes the numbers of days in a month into account when changing values, so the full ISO 8601 duration
    (`P#Y#M#DT#H#M#S`) may be applied.

    Notes:
        This is made *specifically* for date arithmetic. This will never be as efficient as any of the standard types of
        date representation. Only use when advanced duration logic is required that cannot be fully handled by a vanilla
        `timedelta` object.
    """
    @classmethod
    def from_datetime(cls, dt: typing.Union[datetime, pandas.Timestamp]) -> ClockworkDate:
        """
        Create clockwork date based off of the passed in datetime or pandas Timestamp

        Args:
            dt:  The vanilla datetime or pandas Timestamp object to use to create a new Clockwork Date

        Returns:
            A new Clockwork Date object
        """
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)

        return cls(
            year=dt.year,
            month=dt.month,
            day=dt.day,
            hour=dt.hour,
            minute=dt.minute,
            second=dt.second
        )

    @classmethod
    def strptime(cls, date_string: str) -> ClockworkDate:
        """
        Create a new Clockwork Date based on a date string

        Args:
            date_string: The string representing a date

        Returns:
            A newly created Clockwork Date
        """
        date_and_time = parse_date(date_string)
        return cls.from_datetime(date_and_time)

    def __init__(
        self,
        year: int = None,
        month: typing.Union[str, int] = None,
        day: int = None,
        hour: int = None,
        minute: int = None,
        second: int = None
    ):
        """
        Constructor

        Calling the constructor with no parameters yields the first instant of the current year

        Notes:
            All ClockworkDates are measured in UTC

        Args:
            year: The year for the date. Default: this year
            month: The number or name of the month. Default: 1
            day: The number of the day of the month. Default: 1
            hour: The number of the hour of the day. Default: 0
            minute: The number of the minute of the hour. Default: 0
            second: The number of the second of the minute. Default: 0
        """
        # If no year is given, grab the current year
        if year is None:
            year = datetime.utcnow().year

        # If the month is an integer find the number of years and remaining months it represents
        # If one or more whole years are found, those are added to the years and the current month is set to the
        # remainder. If the month given is `14`, `1` is added to the year and the month number becomes `2`
        if _is_integer(month):
            years_from_months, month = divmod(month, 12)
            year += years_from_months

        self.__current_year: Year = Year(year)
        """Object used to manage the expectations for the current year for the date"""

        self.__current_month: Month = Months[month if month is not None else 1]
        """The current month - used to determine how many days to expect"""

        # If seconds are given, find the number of minutes and remaining seconds. If one or more minutes are found,
        # they are added to the number for minutes to increment by later and the number of seconds are set to the
        # remainder. If the given seconds is `150`, the minutes will be incremented by `2` later and the number of
        # seconds becomes `30`.
        if _is_integer(second):
            adjustment_seconds, second = divmod(second, 60)
        else:
            adjustment_seconds = 0

        # If minutes are given, find the number of hours and remaining minutes. If one or more hours are found,
        # they are added to the number for hours to increment by later and the number of minutes are set to the
        # remainder. If the given minutes is 75, the hours will be incremented by `1` later and the number of minutes
        # Becomes 15.
        if _is_integer(minute):
            adjustment_minutes, minute = divmod(minute, 60)
        else:
            adjustment_minutes = 0

        # If hours are given, find the number of days and remaining hours. If one or more days are found, they are
        # added to the number for days to increment by later and the number of days are sent to the remainder. If
        # the given number of hours is 36, the number for the day will be incremented by `1` later and the number
        # of hours will be set to `12`
        if _is_integer(hour):
            adjustment_hours, hour = divmod(hour, 24)
        else:
            adjustment_hours = 0

        # If the number for the day is given and it's greater than the current month, increment the number of
        # exceeding days later and set the expected day to the final day of the month
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
        """The portion of the date representing the current day of the month"""

        self.__current_hour: GroupMember[int] = Hours(
            value=hour,
            on_rollover=self.__hour_rolled_over,
            on_rollback=self.__hour_rolled_back
        )
        """The portion of the date representing the current hour of the day"""

        self.__current_minute: GroupMember[int] = Minutes(
            value=minute,
            on_rollover=self.__minute_rolled_over,
            on_rollback=self.__minute_rolled_back
        )
        """The portion of the date representing the current minute of the hour"""

        self.__current_second: GroupMember[int] = Seconds(
            value=second,
            on_rollover=self.__second_rolled_over,
            on_rollback=self.__second_rolled_back
        )
        """The portion of the date representing the current second of the minute"""

        # If there was an overflow of any unit prior to a month, increment by those now
        # The added event handlers will ensure that any possible compounded overflow will correctly bubble up
        # and increment all higher order values as needed.

        # If there are any adjustment seconds, increment or decrement as needed
        if adjustment_seconds is not None and adjustment_seconds != 0:
            if adjustment_seconds > 0:
                self.__current_second.increment(adjustment_seconds)
            else:
                self.__current_second.decrement(abs(adjustment_seconds))

        # If there are any adjustment minutes, increment or decrement as needed
        if adjustment_minutes is not None and adjustment_minutes != 0:
            if adjustment_minutes > 0:
                self.__current_minute.increment(adjustment_minutes)
            else:
                self.__current_minute.decrement(abs(adjustment_minutes))

        # If there are any adjustment hours, increment or decrement as needed
        if adjustment_hours is not None and adjustment_hours != 0:
            if adjustment_hours > 0:
                self.__current_hour.increment(adjustment_hours)
            else:
                self.__current_hour.decrement(abs(adjustment_hours))

        # If there are any adjustment days, increment or decrement as needed
        if adjustment_days is not None and adjustment_days != 0:
            if adjustment_days > 0:
                self.__current_day.increment(adjustment_days)
            else:
                self.__current_day.decrement(abs(adjustment_days))

    def __second_rolled_over(self, second: GroupMember[int]):
        """
        The event handler for when the number of seconds crosses over from 59 to 60, becoming 0 again

        Args:
            second: The member for the current second
        """
        # Add a minute since the threshold for a minute from the current seconds has been passed
        self.__current_minute.increment()

    def __minute_rolled_over(self, minute: GroupMember[int]):
        """
        The event handler for when the number of minutes crosses over from 59 to 60, becoming 0 again

        Args:
            minute: The member for the current minute
        """
        # Add an hour since the threshold for an hour from the current minutes has been passed
        self.__current_hour.increment()

    def __hour_rolled_over(self, hour: GroupMember[int]):
        """
        The event handler for when the number of hours crosses over from 23 to 24, becoming 0 again

        Args:
            hour: The member for the current hour
        """
        # Add a day since the threshold for a day from the current hours has been passed
        self.__current_day.increment()

    def __day_rolled_over(self, day: GroupMember[int]):
        """
        The event handler for when the number of days has exceeded the number of days in the current month

        Args:
            day: The member representing the current day
        """
        # Add a month since the threshold for the number of days in the month has been passed
        self.__increment_month(day)

    def __day_rolled_back(self, day: GroupMember[int]):
        """
        The event handler for when the number of days has dipped below 1

        Args:
            day: The member representing the current day
        """
        # Remove a month since the day has dipped below the lowest possible value in the month
        self.__decrement_month(day)

    def __hour_rolled_back(self, hour: GroupMember[int]):
        """
        The event handler for when the number of hours has dipped below 0

        Args:
            hour: The member representing the current hour
        """
        # Remove a day since the hour has dipped below the lowest possible value
        self.__current_day.decrement()

    def __minute_rolled_back(self, minute: GroupMember[int]):
        """
        The event handler for when the number of minutes has dipped below 0

        Args:
            minute: The member representing the current minute
        """
        # Remove an hour since the number of minutes has dipped below the lowest possible value
        self.__current_hour.decrement()

    def __second_rolled_back(self, second: GroupMember[int]):
        """
        The event handler for when the number of seconds has dipped below 0

        Args:
            second: The member representing the current second
        """
        # Remove a minute since the number of seconds has dipped below the lowest possible value
        self.__current_minute.decrement()

    def __update_month(self, initial_day_index: int, current_day: GroupMember[int], index: typing.Union[int, str]):
        """
        Update the new value for the month and ensure that not only is the day the correct value but that the day
        iterates over the correct group

        Args:
            initial_day_index: The index for the day at the beginning of any looping month operation
            current_day: The member representing the current day
            index: The index of the new month
        """
        new_month = Months[index]
        days_in_month = new_month(self.year)

        # If the index of the original day used in this month operation exists within this month, use that one.
        # Say we are incrementing from 2 months from January 30th. There is no February 30th, so incrementing to
        # February would mean backing down to February 28th. Next we move from February to March, which has a 30th.
        # Move on to that 30th to restore to original position.
        if initial_day_index <= days_in_month.final_index:
            day_index = initial_day_index
        elif current_day == self.__current_month(self.year).max and current_day > days_in_month.max:
            # Use the final day in the new month if the current day is larger than the maximum value in the new month
            # For example, say we are on March 30th and need to go back a month. The previous month, February, only
            # has 28 days in the example. Since there is no February 30th, use the max (i.e. the 28th)
            day_index = days_in_month.final_index
        else:
            day_index = current_day.index

        self.__current_month = new_month
        current_day.switch_group(
            new_group=days_in_month,
            new_index=day_index
        )

    def __increment_month(self, current_day: GroupMember[int], amount: int = 0):
        """
        Move on to the next month

        Args:
            current_day: The member representing the current day
            amount: The amount of months to increment by. Default = 1
        """
        if amount is None:
            amount = 1

        # Ideally, we want to stay on the same day from month to month. Record this day in order to return to it
        # if/when possible.
        initial_day_index = current_day.index

        while amount > 0:
            next_index = self.month + 1

            # If the index of the month will go beyond 12 (the highest possible index), increment the year and set
            # the value for the next month to 1 to signify that the month has reset to the beginning
            if next_index > 12:
                self.__current_year.increment()
                next_index = 1

            self.__update_month(initial_day_index=initial_day_index, current_day=current_day, index=next_index)

            amount -= 1

    def __decrement_month(self, current_day: GroupMember[int], amount: int = 0):
        """
        Move to the previous month

        Args:
            current_day: The member representing the current day of the month
            amount: The amount of months to decrement. Default: 1
        """
        if amount is None:
            amount = 1

        # Ideally, we want to stay on the same day from month to month. Record this day in order to return to it
        # if/when possible.
        initial_day_index = current_day.index

        while amount > 0:
            next_index = self.month - 1

            # If the month dips below one, we've moved from January to December, moving from one year to the previous.
            # Reduce the year and set the month to the highest index to reflect that.
            if next_index < 1:
                self.__current_year.decrement()
                next_index = 12

            self.__update_month(initial_day_index=initial_day_index, current_day=current_day, index=next_index)

            amount -= 1

    @property
    def year(self):
        """
        The number for the current year
        """
        return self.__current_year.year

    @property
    def month(self):
        """
        The number for the current month
        """
        return self.__current_month.number

    @property
    def month_name(self) -> str:
        """
        The name of the current month
        """
        return self.__current_month.name

    @property
    def day(self) -> int:
        """
        The number for the current day of the month
        """
        return self.__current_day.value

    @property
    def hour(self) -> int:
        """
        The number of the current hour of the day
        """
        return self.__current_hour.value

    @property
    def minute(self) -> int:
        """
        The number of the current minute in the hour
        """
        return self.__current_minute.value

    @property
    def second(self) -> int:
        """
        The number of the current second in a minute
        """
        return self.__current_second.value

    def __add_timedelta(self, delta: timedelta) -> Self:
        """
        Add a timedelta representation of a duration to this date

        Args:
            delta: The timedelta duration

        Returns:
            The updated instance
        """
        # We want as few interation operations as possible, so decompose all possible iterations into seconds,
        # minutes, hours, and days
        minutes, seconds = divmod(delta.total_seconds(), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        # Increment each portion separately, in order, so that incrementing one unit as a side effect of another
        # increment is properly handled.
        self.__current_second.increment(seconds)
        self.__current_minute.increment(minutes)
        self.__current_hour.increment(hours)
        self.__current_day.increment(days)
        return self

    def __add_relative_duration(self, duration: RelativeDuration) -> Self:
        """
        Add a relative duration to this date

        Args:
            duration: The duration to add

        Returns:
            The updated instance
        """
        # Increment each portion separately, in order, so that incrementing one unit as a side effect of another
        # increment is properly handled.
        self.__current_second.increment(duration.seconds)
        self.__current_minute.increment(duration.minutes)
        self.__current_hour.increment(duration.hours)
        self.__current_day.increment(duration.days)
        self.__increment_month(self.__current_day, duration.months)
        self.__current_year.increment(duration.years)
        return self

    def __subtract_timedelta(self, delta: timedelta) -> Self:
        """
        Remove a vanilla timedelta duration from this date

        Args:
            delta: The amount of time to remove from this date

        Returns:
            The updated instance
        """
        # We want as few interation operations as possible, so decompose all possible iterations into seconds,
        # minutes, hours, and days
        minutes, seconds = divmod(delta.total_seconds(), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        # decrement each portion separately, in order, so that decrementing one unit as a side effect of another
        # decrement is properly handled.
        self.__current_second.decrement(seconds)
        self.__current_minute.decrement(minutes)
        self.__current_hour.decrement(hours)
        self.__current_day.decrement(days)
        return self

    def __subtract_relative_duration(self, duration: RelativeDuration) -> Self:
        """
        Remove a relative duration to this date

        Args:
            duration: The duration to remove

        Returns:
            The updated instance
        """
        # Decrement each portion separately, in order, so that decrementing one unit as a side effect of another
        # decrement is properly handled.
        self.__current_second.decrement(duration.seconds)
        self.__current_minute.decrement(duration.minutes)
        self.__current_hour.decrement(duration.hours)
        self.__current_day.decrement(duration.days)
        self.__decrement_month(self.__current_day, duration.months)
        self.__current_year.decrement(duration.years)
        return self

    def to_timestamp(self, tz: tzinfo = None) -> pandas.Timestamp:
        """
        Convert this date into a pandas Timestamp class

        Args:
            tz: An optional timezone to attach to the Timestamp

        Returns:
            This date in the pandas Timestamp format
        """
        # The underlying timezone for a Clockwork date is UTC, so if a timezone is passed with the intention of
        # creating a timezone aware date, first create the datetime object in UTC and convert to the proper timezone
        # afterwards.
        timestamp = pandas.Timestamp(
            year=self.__current_year.year,
            month=self.__current_month.number,
            day=self.__current_day.value,
            hour=self.__current_hour.value,
            minute=self.__current_minute.value,
            second=self.__current_second.value,
            tz=timezone.utc if tz else None
        )

        if tz:
            timestamp = timestamp.astimezone(tz=tz)

        return timestamp

    def to_datetime(self, tz: tzinfo = None) -> datetime:
        """
        Convert this date into a vanilla datetime

        Args:
            tz: An optional timezone to attach to the datetime

        Returns:
            This date in the vanilla datetime format
        """
        # The underlying timezone for a Clockwork date is UTC, so if a timezone is passed with the intention of
        # creating a timezone aware date, first create the datetime object in UTC and convert to the proper timezone
        # afterwards.
        dt = datetime(
            year=self.__current_year.year,
            month=self.__current_month.number,
            day=self.__current_day.value,
            hour=self.__current_hour.value,
            minute=self.__current_minute.value,
            second=self.__current_second.value,
            tzinfo=timezone.utc if tz else None
        )

        if tz:
            dt = dt.astimezone(tz=tz)

        return dt

    def strftime(self, __format: str, *, tz:tzinfo = None) -> str:
        """
        Convert this into a formatted string

        Format codes may be found at https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes

        Args:
            __format: The string instructing how to format this date
            tz: An optional timezone to attach to the date prior to formatting

        Returns:
            A formatted string representation for this date
        """
        dt = self.to_datetime(tz=tz)
        return dt.strftime(__format)

    def __add__(self, other: typing.Union[RelativeDuration, timedelta, str]) -> ClockworkDate:
        if isinstance(other, str):
            other = RelativeDuration.from_string(other)

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

    @typing.overload
    def __sub__(self, other: typing.Union[RelativeDuration, timedelta, str]) -> ClockworkDate:
        ...

    @typing.overload
    def __sub__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp]) -> RelativeDuration:
        ...

    def __sub__(
        self,
        other: typing.Union[RelativeDuration, timedelta, ClockworkDate, datetime, pandas.Timestamp, str]
    ) -> typing.Union[ClockworkDate, RelativeDuration]:
        if isinstance(other, str):
            other = RelativeDuration.from_string(other)

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
        elif isinstance(other, (ClockworkDate, datetime, pandas.Timestamp)):
            normalized_date = normalize_datetime(other)
            return RelativeDuration(
                years=self.year - normalized_date.year,
                months=self.month - normalized_date.month,
                days=self.day - normalized_date.day,
                hours=self.hour - normalized_date.hour,
                minutes=self.minute - normalized_date.minute,
                seconds=self.second - normalized_date.second
            )

        raise TypeError(
            f"May only add a RelativeDuration or timedelta to a {self.__class__.__name__}. "
            f"Received '{other}: {type(other)}'"
        )

    def __iadd__(self, other: typing.Union[RelativeDuration, timedelta, str]) -> ClockworkDate:
        if isinstance(other, str):
            other = RelativeDuration.from_string(other)

        if isinstance(other, RelativeDuration):
            return self.__add_relative_duration(other)
        elif isinstance(other, timedelta):
            return self.__add_timedelta(other)

        raise TypeError(
            f"May only add a RelativeDuration or timedelta to a {self.__class__.__name__}. "
            f"Received '{other}: {type(other)}'"
        )

    def __isub__(self, other: typing.Union[RelativeDuration, timedelta, str]) -> ClockworkDate:
        if isinstance(other, str):
            other = RelativeDuration.from_string(other)

        if isinstance(other, RelativeDuration):
            return self.__subtract_relative_duration(other)
        elif isinstance(other, timedelta):
            return self.__subtract_timedelta(other)

        raise TypeError(
            f"May only add a RelativeDuration or timedelta to a {self.__class__.__name__}. "
            f"Received '{other}: {type(other)}'"
        )

    def __eq__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp, str]) -> bool:
        other = normalize_datetime(other)
        return self.year == other.year \
            and self.month == other.month \
            and self.day == other.day \
            and self.hour == other.hour \
            and self.minute == other.minute \
            and self.second == other.second

    def __ne__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp, str]) -> bool:
        other = normalize_datetime(other)
        return self.year != other.year \
            or self.month != other.month \
            or self.day != other.day \
            or self.hour != other.hour \
            or self.minute != other.minute \
            or self.second != other.second

    def __lt__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp, str]) -> bool:
        other = normalize_datetime(other)

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

    def __le__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp, str]) -> bool:
        other = normalize_datetime(other)

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

    def __gt__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp, str]) -> bool:
        other = normalize_datetime(other)

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

    def __ge__(self, other: typing.Union[ClockworkDate, datetime, pandas.Timestamp, str]) -> bool:
        other = normalize_datetime(other)

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

    def __str__(self):
        return f"{self.year}-{self.month}-{self.day} {self.hour}:{self.minute}:{self.second}-0000"

    def __repr__(self):
        return f"[{self.__class__.__name__}] (" \
               f"year={self.year}, " \
               f"month={self.month}, " \
               f"day={self.day}, " \
               f"hour={self.hour}, " \
               f"minute={self.minute}, " \
               f"second={self.second}" \
               f")"