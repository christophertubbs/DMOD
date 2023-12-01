"""
Defines a finite group and objects that operate upon and within them
"""
from __future__ import annotations

import calendar
import typing
from datetime import datetime
from datetime import timedelta
from typing import Iterator

from dateutil.parser import parse as parse_date

import numpy
import pandas
from dmod.core.common import on_each

from .duration import RelativeDuration
from .string import CaseInsensitiveString

T = typing.TypeVar("T")


def _is_integer(value) -> bool:
    return numpy.issubdtype(type(value), numpy.integer)


def _value_is_comparable(other) -> bool:
    return _is_integer(other) or isinstance(other, GroupMember)


class FiniteGroup(typing.Generic[T]):
    @classmethod
    def of_value(cls, name: str, group: typing.Collection[T], value: T) -> GroupMember[T]:
        finite_group = cls(name, group)
        member = finite_group(value)
        return member

    def __init__(self, name: str, group: typing.Collection[T]):
        if group is None or len(group) == 0:
            raise ValueError(f'The definition for a finite group requires a defined set of values')

        self.__name = name
        self.__group = [value for value in group]
        self.__length = len(group)
        self.__hash = hash((
            value if isinstance(value, typing.Hashable) else repr(value)
            for value in self.__group
        ))

    @property
    def first(self) -> GroupMember[T]:
        return GroupMember(self, 0)

    @property
    def last(self) -> GroupMember[T]:
        return GroupMember(self, -1)

    @property
    def name(self) -> str:
        return self.__name

    @property
    def final_index(self) -> int:
        return self.__length - 1

    @property
    def max(self) -> T:
        return self.__group[-1]

    @property
    def min(self) -> T:
        return self.__group[0]

    @property
    def members(self) -> typing.Iterable[GroupMember[T]]:
        return [
            self(value)
            for value in self.__group
        ]

    def find(self, predicate: typing.Callable[[T], bool]) -> typing.Optional[GroupMember[T]]:
        for index, value in enumerate(self.__group):
            if predicate(value):
                return GroupMember(self, index)

        return None

    def index_of(self, value_to_find: T) -> int:
        for value_index in range(self.__length):
            if self.__group[value_index] == value_to_find:
                return value_index
        raise KeyError(f"'{value_to_find}' is not a member of this group")

    def by_index(self, index: int) -> GroupMember[T]:
        index = self.absolute_index(index)
        return GroupMember(self, index)

    def absolute_index(self, index: int) -> int:
        if not _is_integer(index):
            raise TypeError(f"Raw indices for FiniteGroups must be integers")

        if index < 0:
            while index < 0:
                index = self.__length + index
        else:
            index = index % self.__length

        return index

    def get(self, value_or_index: typing.Union[int, T]) -> GroupMember[T]:
        if value_or_index in self:
            return GroupMember(self, self.index_of(value_or_index))
        elif not _is_integer(value_or_index):
            raise ValueError(f"'{value_or_index}' is not a member of the group named '{self.name}'")
        return self.by_index(value_or_index)

    def get_by_range(self, index_range: slice) -> typing.Sequence[GroupMember[T]]:
        retrieved_values: typing.List[T] = list()
        step = index_range.step or 1

        current_index = index_range.start

        while current_index < index_range.stop:
            retrieved_values.append(self.by_index(current_index))
            current_index += step

        return retrieved_values

    def raw_value(self, index: int) -> T:
        if not _is_integer(index):
            raise TypeError(
                f"Raw values may only be obtained from the {self.name} group by integer indices. "
                f"Received '{type(index)}'"
            )
        real_index = self.absolute_index(index)
        return self.__group[real_index]

    def __iter__(self):
        return iter(self.members)

    @typing.overload
    def __getitem__(self, index: slice) -> typing.Sequence[GroupMember[T]]:
        ...

    @typing.overload
    def __getitem__(self, index: int) -> GroupMember[T]:
        ...

    def __getitem__(
        self,
        index: typing.Union[slice, int, T]
    ) -> typing.Union[typing.Sequence[GroupMember[T]], GroupMember[T]]:
        if isinstance(index, slice):
            return self.get_by_range(index)
        return self.get(index)

    def __len__(self):
        return self.__length

    def __contains__(self, item):
        return any([value == item for value in self.__group])

    def __str__(self):
        if len(self) <= 4:
            return f"[{self.name}] => " + "{" + ', '.join([str(value) for value in self.__group]) + "}"
        else:
            return f"[{self.name}] => " + "{" + \
                f'{", ".join([str(value) for value in self.__group[:2]])}, ' \
                f'..., ' \
                f'{", ".join([str(value) for value in self.__group[-2:]])}' + \
                "}"

    def __call__(
        self,
        value: T = None,
        *,
        on_rollover: typing.Union[
            MemberLoopHandler,
            typing.Iterable[MemberLoopHandler]
        ] = None,
        on_rollback: typing.Union[
            MemberLoopHandler,
            typing.Iterable[MemberLoopHandler]
        ] = None
    ) -> GroupMember[T]:
        if value is None:
            new_index = 0
        else:
            new_index = self.index_of(value)

        return GroupMember(
            group=self,
            index=new_index,
            on_rollover=on_rollover,
            on_rollback=on_rollback
        )

    def __repr__(self):
        return self.__str__()

    def __hash__(self):
        return self.__hash

    def __eq__(self, other):
        if not isinstance(other, FiniteGroup):
            return False

        return self.__hash == other.__hash


class GroupMember(typing.Generic[T]):
    def __init__(
        self,
        group: FiniteGroup[T],
        index: int = None,
        *,
        on_rollover: typing.Union[MemberLoopHandler, typing.Iterable[MemberLoopHandler]] = None,
        on_rollback: typing.Union[MemberLoopHandler, typing.Iterable[MemberLoopHandler]] = None
    ):
        if not isinstance(group, FiniteGroup):
            raise TypeError(f"Cannot create a member of a group - no group was given")

        if not _is_integer(index):
            raise TypeError(f"Cannot create a member of a group - the index was not valid")

        self.__group = group
        self.__current_index = group.absolute_index(index) if index is not None else 0

        if isinstance(on_rollover, typing.Callable):
            self.__on_rollover = [on_rollover]
        else:
            self.__on_rollover: typing.List[MemberLoopHandler] = [
                handler
                for handler in on_rollover or []
            ]

        if isinstance(on_rollback, typing.Callable):
            self.__on_rollback = [on_rollback]
        else:
            self.__on_rollback: typing.List[MemberLoopHandler] = [
                handler
                for handler in on_rollback or []
            ]

    def add_rollover_handler(self, handler: MemberLoopHandler):
        self.__on_rollover.append(handler)

    def add_reverse_loop_handler(self, handler: MemberLoopHandler):
        self.__on_rollback.append(handler)

    @property
    def group(self) -> FiniteGroup[T]:
        return self.__group

    @property
    def index(self) -> int:
        return self.__current_index

    @property
    def value(self) -> T:
        return self.__group.raw_value(self.__current_index)

    def __rollover(self, previous_index: typing.Optional[int], new_index: int):
        on_each(lambda function: function(previous_index, new_index), self.__on_rollover)

    def __rollback(self, previous_index: typing.Optional[int], new_index: int):
        on_each(lambda function: function(previous_index, new_index), self.__on_rollback)

    def increment(self, amount: int = None):
        if amount is None:
            amount = 1

        while amount > 0:
            previous_index = self.__current_index
            self.__current_index += 1

            if self.__current_index > self.__group.final_index:
                self.__current_index = 0
                self.__rollover(previous_index, self.__current_index)

            amount -= 1

        return self

    def decrement(self, amount: int = None):
        if amount is None:
            amount = 1

        while amount > 0:
            previous_index = self.__current_index
            self.__current_index -= 1

            if self.__current_index < 0:
                self.__current_index = self.__group.final_index
                self.__rollback(previous_index=previous_index, new_index=self.__current_index)

            amount -= 1

        return self

    def switch_group(self, new_group: FiniteGroup[T], new_index: int = None):
        if new_index is not None and not _is_integer(new_index):
            raise TypeError(f"Cannot assign a new index for a new group - the new index is not an integer")

        self.__group = new_group

        if new_index is not None:
            self.__current_index = new_group.absolute_index(new_index)

    def __update_index(self, index: int):
        absolute_index = self.group.absolute_index(index)
        self.__current_index = absolute_index

    def __add__(self, other: typing.Union[int, GroupMember[T]]) -> GroupMember[T]:
        if not _value_is_comparable(other):
            raise TypeError(
                f"Can only add an integer or another member to a GroupMember - received '{other}: {type(other)}'"
            )

        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        if isinstance(other, GroupMember):
            return self.group.by_index(self.index + other.index)

        return self.group.by_index(self.index + other)

    def __sub__(self, other: typing.Union[int, GroupMember[T]]) -> GroupMember[T]:
        if not _value_is_comparable(other):
            raise TypeError(
                f"Can only subtract an integer or another member from a GroupMember - received '{other}: {type(other)}'"
            )

        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        if not isinstance(other, GroupMember):
            other = self.group.get(other)

        return self.group.by_index(self.index - other.index)

    def __lt__(self, other: typing.Union[T, GroupMember[T]]) -> bool:
        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        if isinstance(other, GroupMember):
            return self.index < other.index

        return self.value < other

    def __le__(self, other: typing.Union[T, GroupMember[T]]) -> bool:
        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        if isinstance(other, GroupMember):
            return self.index <= other.index

        return self.value <= other

    def __gt__(self, other: typing.Union[T, GroupMember[T]]) -> bool:
        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot compare members of two different groups")

        if isinstance(other, GroupMember):
            return self.index > other.index

        return self.value > other

    def __ge__(self, other: typing.Union[T, GroupMember[T]]) -> bool:
        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        if isinstance(other, GroupMember):
            return self.index >= other.index

        return self.value >= other

    def __eq__(self, other: typing.Union[GroupMember[T], T]) -> bool:
        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        if isinstance(other, GroupMember):
            return self.index == other.index

        return self.value == other

    def __ne__(self, other: typing.Union[GroupMember[T], T]) -> bool:
        if isinstance(other, GroupMember) and self.group != other.__group:
            raise TypeError(f"Cannot compare values from nonequivalent groups")

        if isinstance(other, GroupMember):
            return self.index == other.index

        return self.value != other

    def __isub__(self, other: typing.Union[int, GroupMember[T]]) -> GroupMember[T]:
        if not _value_is_comparable(other):
            raise TypeError(
                f"May only subtract integers or other members from a GroupMember. Received {other}: {type(other)}"
            )

        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        if not isinstance(other, GroupMember):
            other = self.group.get(other)

        self.decrement(other.index)
        return self

    def __iadd__(self, other: typing.Union[int, GroupMember[T]]) -> GroupMember[T]:
        if not _value_is_comparable(other):
            raise TypeError(f"May only add integers or other members to a GroupMember. Received {type(other)}")

        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot increment a group value by the value of another group")

        if not isinstance(other, GroupMember):
            other = self.group.get(other)

        self.increment(other.index)
        return self

    def update_by_value(self, value: T):
        index = self.group.index_of(value)
        self.__current_index = index

    def update_by_index(self, index: int):
        self.__current_index = self.group.absolute_index(index)

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return self.__str__()

    def __bool__(self):
        return self.index != 0


MemberLoopHandler = typing.Callable[[typing.Any, ...], typing.Any]
