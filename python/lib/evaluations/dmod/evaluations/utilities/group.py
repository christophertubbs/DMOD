"""
Defines a circular finite group and objects that operate upon and within them

The two pieces are the `FiniteGroup` and a `GroupMember`. A `GroupMember` points to a value within a `FiniteGroup`.

Imagine:

=========  ====================
  Value      Members
---------  --------------------
    1
    2
    3        Member A
    4
    5       Member B, Member C
    6
    7        Member D
=========  ====================

Member A represents 3, members B and C represent 5 independently, and member D represents 7. If member C is
incremented by 2, member C now represents 7. Members B and D do not change in any way. If member D is incremented by 2,
member D now represents 2 since it has incremented beyond the bounds of the group and has looped back around
"""
from __future__ import annotations

import typing

from typing_extensions import Self
from typing_extensions import ParamSpec
from typing_extensions import Concatenate

from ..util import is_integer
from dmod.core.common import on_each

T = typing.TypeVar("T")
ARGS_KWARGS = ParamSpec("ARGS_KWARGS")


class FiniteGroup(typing.Generic[T]):
    """
    Represents a finite, circular group of ordered values that may be iterated through.

    Given a group of:

        g = [1, "A", 3, True, 43, "b", False]

    Then `g(0)` would be the value `1`. `g(6)` would be `False`. Where this differs from a normal collection is
    that `g(7)` does not yield some sort of out of range exception. Instead, `g(7)` is `1`. The index of `7` looped
    over and starts again at the beginning. Similarly, `g(-8)` is `False` since that, too, loops over.

    A group is considered a whole value space. If (-infinity, infinity) is the entire value space for an integer and
    an integer may be any integer held within, `[1, "A", 3, True, 43, "b", False]` is an entire value space for a
    member of said group and a member may be any value held within.

    A group is considered immutable. Referencing a value from within a group is done via a GroupMember.
    A GroupMember is a glorified pointer to a value within the group. Operations performed on values within the group
    are performed upon GroupMembers to ensure that the rules of a FiniteGroup (such as value looping) are enforced.
    """
    @classmethod
    def of_value(cls, name: str, group: typing.Collection[T], value: T = None) -> GroupMember[T]:
        """
        Create a group and a member of said group based on the desired value

        Args:
            name: The name of the group to create
            group: The values that should belong to the group
            value: The desired value to point to within the group

        Returns:
            A member of said group
        """
        finite_group = cls(name, group)
        member = finite_group(value)
        return member

    def __init__(self, name: str, group: typing.Collection[T]):
        """
        Constructor

        Args:
            name: The name of the group
            group: The values that the group will contain
        """
        if group is None or len(group) == 0:
            raise ValueError(f'The definition for a finite group requires a defined set of values')

        self.__group: typing.List[T] = []
        """The raw values of the group"""

        for value in group:
            if value in group:
                raise Exception(
                    f"A duplicate value was encountered when constructing a FiniteGroup named {name}. "
                    f"Values in a finite group must be unique."
                )
            self.__group.append(value)

        self.__name = name
        """The name of the group"""

        self.__length = len(group)
        """The length of the group"""

        self.__hash = hash((
            value if isinstance(value, typing.Hashable) else repr(value)
            for value in self.__group
        ))
        """The unique hash based upon the values held within"""

    @property
    def first(self) -> GroupMember[T]:
        """
        The first member of the group
        """
        return GroupMember(self, 0)

    @property
    def last(self) -> GroupMember[T]:
        """
        The last member of the group
        """
        return GroupMember(self, -1)

    @property
    def name(self) -> str:
        """
        The name of the group
        """
        return self.__name

    @property
    def final_index(self) -> int:
        """
        The last possible index within the group
        """
        return self.__length - 1

    @property
    def max(self) -> T:
        """
        The largest raw value within the group. Groups are considered ordered,
        so the largest value in `[5, 4, 3, 2, 1]` would be `1`, not `5`.
        """
        return self.__group[-1]

    @property
    def min(self) -> T:
        """
        The smallest raw value within the group. Groups are considered ordered, so the smallest value in
        `[5, 4, 3, 2, 1]` would be `5`, not `1`.
        """
        return self.__group[0]

    @property
    def members(self) -> typing.Iterable[GroupMember[T]]:
        """
        A collection of all values within the group, in group order
        """
        return [
            self(value)
            for value in self.__group
        ]

    def find(self, predicate: typing.Callable[[int, T], bool]) -> typing.Optional[GroupMember[T]]:
        """
        Find the first member of the group that matches the given predicate

        Args:
            predicate: A function in the form of (index, value) => bool that determines if the identified value is the
                value of interest

        Returns:
            The first value of interest if it is found
        """
        for index, value in enumerate(self.__group):
            if predicate(index, value):
                return GroupMember(self, index)

        return None

    def find_all(self, predicate: typing.Callable[[int, T], bool]) -> typing.Sequence[GroupMember[T]]:
        """
        Find all members of the group that match the given predicate

        Args:
            predicate: A function in the form of (index, value) => bool that determines if the identified value is the
                value of interest

        Returns:
            All members of the group that match the given predicate
        """
        matches: typing.List[GroupMember[T]] = list()

        for index, value in enumerate(self.__group):
            if predicate(index, value):
                matches.append(GroupMember(self, index))

        return matches

    def index_of(self, value_to_find: T) -> int:
        """
        Find the index of the value of interest

        Args:
            value_to_find: The value to find

        Returns:
            The index of the value within the group
        """
        for value_index in range(self.__length):
            if self.__group[value_index] == value_to_find:
                return value_index
        raise KeyError(f"'{value_to_find}' is not a member of this group")

    def by_index(self, index: int) -> GroupMember[T]:
        """
        Create a member of the group based on the index of its value

        Args:
            index: Where the value of interest lies within the group

        Returns:
            A GroupMember pointing to the value of interest
        """
        index = self.absolute_index(index)
        return GroupMember(self, index)

    def absolute_index(self, index: int) -> int:
        """
        Get the `intended` index of a value that based on an index that may or may not be out of range

        Given an index of `12` and a group of `[5, 6, 7, 8]`, `FiniteGroup.absolute_index(12)` will return `5`,
        considering that `12` loops over the collection several times

        Args:
            index: An index that is intended to be used to reference values

        Returns:
            An index within the bounds of the group
        """
        if not is_integer(index):
            raise TypeError(f"Raw indices for FiniteGroups must be integers")

        index = index % self.__length

        return index

    def get(self, value_or_index: typing.Union[int, T]) -> GroupMember[T]:
        """
        Get a member of the group based on either the intended value or its index

        Args:
            value_or_index: Either the value to find or an index of it

        Returns:
            A GroupMember pointing to the value of interest
        """
        if value_or_index in self:
            return GroupMember(self, self.index_of(value_or_index))
        elif not is_integer(value_or_index):
            raise ValueError(f"'{value_or_index}' is not a member of the group named '{self.name}'")
        return self.by_index(value_or_index)

    def get_by_range(self, index_range: slice) -> typing.Sequence[GroupMember[T]]:
        """
        Get all values within the group that comply with the given slice

        Examples:
            >>> group = FiniteGroup("example", [5, 6, 7, 8, 9, 20])
            >>> group[3:]
            [8, 9, 20]
            >>> group[3:8]
            [8, 9, 20]
            >>> group[14:]
            [7, 8, 9, 20]
            >>> group[14:8]
            []

        Args:
            index_range: The range of values to retrieve

        Returns:
            All members between the passed absolute indices
        """
        step = index_range.step or 1
        start_index = self.absolute_index(index_range.start)
        stop_index = self.absolute_index(index_range.stop or self.__length)

        return [
            self.by_index(index)
            for index in range(start_index, stop_index, step)
        ]

    def raw_value(self, index: int) -> T:
        """
        Get the actual value based on the index rather than a member representing it

        Args:
            index: The index of the value to retrieve

        Returns:
            The raw value at the given index
        """
        if not is_integer(index):
            raise TypeError(
                f"Raw values may only be obtained from the {self.name} group by integer indices. "
                f"Received '{type(index)}'"
            )
        real_index = self.absolute_index(index)
        return self.__group[real_index]

    def __iter__(self):
        """
        Iterate over all members of the group (not the values)

        Returns:
            An iterable collection of all members of the group (not the values)
        """
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
        """
        Create a member for the group

        Giving not `value` is like just calling `int()` - a member for the zeroth value will be returned as the default

        Args:
            value: The value of the group to create a member for
            on_rollover: Extra actions to perform when the index for the member rolls over the largest viable index
            on_rollback: Extra actions to perform with the index for the member rolls below the smallest viable index

        Returns:
            A Group member pointing at the desired value
        """
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
        """
        Two groups are considered equal if they contain the same values in the same order. The name is not
        considered since all operations will yield the same values.

        Args:
            other: The other item to compare to

        Returns:
            Whether this group is equal to the other item
        """
        if not isinstance(other, FiniteGroup):
            return False

        return self.__hash == other.__hash

    def __ne__(self, other):
        """
        Two groups are considered equal if they contain the same values in the same order. The name is not
        considered since all operations will yield the same values.

        Args:
            other: The other item to compare to

        Returns:
            Whether this group is not equal to the other item
        """
        if not isinstance(other, FiniteGroup):
            return False

        return self.__hash != other.__hash


class GroupMember(typing.Generic[T]):
    """
    Represents a member pointing to a value within a group

    A GroupMember is a wrapper class pointing to the value at an index within a group.

    Given a group of `g = [5, 4, 3, 2, 1]` and a member `m` representing `4` within that group, that member may
    contain the value of 4, but any operations upon the member treat `4` as the value at index `1`, not the
    value of `4`. As a result `4 - 1` is `3`, but `m - 1` is `5` since subtracting `1` from the group member
    shifts the member from index 1 to index 0.
    """
    @classmethod
    def __other_value_is_comparable(cls, other) -> bool:
        """
        Determines if another value is comparable to this member

        Args:
            other: Either the index of another value or another member

        Returns:
            True if `other` is comparable to this member
        """
        return is_integer(other) or isinstance(other, GroupMember)

    def __init__(
        self,
        group: FiniteGroup[T],
        index: int = None,
        *,
        on_rollover: typing.Union[MemberLoopHandler, typing.Iterable[MemberLoopHandler]] = None,
        on_rollback: typing.Union[MemberLoopHandler, typing.Iterable[MemberLoopHandler]] = None
    ):
        """
        Constructor

        Args:
            group: The group that this will be a member of
            index: The index of the group that this member points to
            on_rollover: Extra actions to perform when looping over the maximum viable index
            on_rollback: Extra actions to perform when looping below the lowest viable index
        """
        if not isinstance(group, FiniteGroup):
            raise TypeError(f"Cannot create a member of a group - no group was given")

        if not is_integer(index):
            raise TypeError(f"Cannot create a member of a group - the index was not valid")

        self.__group = group
        """The group containing the values to point to"""

        self.__current_index = group.absolute_index(index) if index is not None else 0
        """The index of the value that this member currently represents"""

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

    def add_rollover_handler(self, handler: MemberLoopHandler) -> Self:
        """
        Attach a new rollover handler to this member

        Args:
            handler: An extra action to perform when rolling over the largest viable index

        Returns:
            This updated instance
        """
        self.__on_rollover.append(handler)
        return self

    def add_rollback_handler(self, handler: MemberLoopHandler) -> Self:
        """
        Attach a new rollback handler to this member

        Args:
            handler: An extra action to perform when rolling back below the minimum viable index

        Returns:
            This updated instance
        """
        self.__on_rollback.append(handler)
        return self

    @property
    def group(self) -> FiniteGroup[T]:
        """
        The group that this is a member of
        """
        return self.__group

    @property
    def index(self) -> int:
        """
        The index of the group that this member is pointing at
        """
        return self.__current_index

    @property
    def value(self) -> T:
        """
        The raw value that this member points to
        """
        return self.__group.raw_value(self.__current_index)

    def __rollover(self):
        """
        Execute all attached rollover logic
        """
        on_each(lambda function: function(self), self.__on_rollover)

    def __rollback(self):
        """
        Execute all attached rollback logic
        """
        on_each(lambda function: function(self), self.__on_rollback)

    def increment(self, amount: int = None) -> Self:
        """
        Increment the index of this member

        Args:
            amount: the number of indices to increment by. Default=1

        Returns:
            The updated instance
        """
        if amount is None:
            amount = 1
        elif amount < 0:
            # This is an analog for an addition operation. Adding a negative results in subtraction,
            # so decrement the absolute value to mimic that operation
            return self.decrement(abs(amount))

        # Loop over instead of just setting the updated index to ensure that rollover logic is called the
        # correct number of times with the correct internal state
        while amount > 0:
            self.__current_index += 1

            if self.__current_index > self.__group.final_index:
                self.__current_index = 0
                self.__rollover()

            amount -= 1

        return self

    def decrement(self, amount: int = None) -> Self:
        """
        Decrement the index of this member

        Args:
            amount: The number of indices to decrement by. Default=1

        Returns:
            The updated instance
        """
        if amount is None:
            amount = 1
        elif amount < 0:
            # This is an analog for a subtraction operation. Subtracting a negative results in addition,
            # so increment the absolute value to mimic that operation
            return self.increment(abs(amount))

        # Loop over instead of just setting the updated index to ensure that rollover logic is called the correct
        # number of times with the correct internal state.
        while amount > 0:
            self.__current_index -= 1

            if self.__current_index < 0:
                self.__current_index = self.__group.final_index
                self.__rollback()

            amount -= 1

        return self

    def switch_group(self, new_group: FiniteGroup[T], new_index: int = None) -> Self:
        """
        Change the group that this member points to

        Use Case:
            An external event changes the limits for what this should point to. For example, say that this represents
            the days in the month of June (30 days) and the set needs to change to July (31 days).

        Args:
            new_group: The new group to point to
            new_index: The new index to use

        Returns:
            The updated instance
        """
        if new_index is not None and not is_integer(new_index):
            raise TypeError(f"Cannot assign a new index for a new group - the new index is not an integer")

        self.__group = new_group

        if new_index is not None:
            self.__current_index = new_group.absolute_index(new_index)
        elif self.__current_index > new_group.final_index:
            self.__current_index = new_group.final_index

        return self

    def __add__(self, other: typing.Union[int, GroupMember[T]]) -> GroupMember[T]:
        """
        Add another group member or number of indices to this member to create a new member

        Args:
            other: Either a number of indices to move or another GroupMember containing the indices that should be added

        Returns:
            A brand-new group member
        """
        if not self.__other_value_is_comparable(other):
            raise TypeError(
                f"Can only add an integer or another member to a GroupMember - received '{other}: {type(other)}'"
            )

        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        # Simply add the indices together to get the next value if the other item is a member of this group
        if isinstance(other, GroupMember):
            return self.group.by_index(self.index + other.index)

        # If this isn't a group member, this should be an int, so add that int to this index
        return self.group.by_index(self.index + other)

    def __sub__(self, other: typing.Union[int, GroupMember[T]]) -> GroupMember[T]:
        """
        Subtract another group member or number of indices to this number to create a new member

        Args:
            other: Either a number of indices to move or another GroupMember containing the indices that should be
                subtracted

        Returns:
            A brand-new GroupMember
        """
        if not self.__other_value_is_comparable(other):
            raise TypeError(
                f"Can only subtract an integer or another member from a GroupMember - received '{other}: {type(other)}'"
            )

        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        if not isinstance(other, GroupMember):
            other = self.group.get(other)

        return self.group.by_index(self.index - other.index)

    def __lt__(self, other: typing.Union[T, GroupMember[T]]) -> bool:
        """
        Determines if this member is less than the other value

        This item is considered less than the other value if:
            - The other item is a group member with a greater index
            - The other item is contained within the group and has a greater index
            - The other item is greater than the value of this member

        Examples:
            >>> group = FiniteGroup("example", [1, "two", 3, "four", 5, "six"])
            >>> member = group("four")
            >>> member < "two"
            False
            >>> member < 5
            True
            >>> member < "ninety"
            True
            >>> member < group(1)
            False
            >>> member < GroupMember(group, 0)
            False
            >>> member < GroupMember(group, 4)
            True

        Args:
            other: The value to compare to

        Returns:
            True if this index or value is lower than the value to compare to
        """
        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot compare members of two different groups")

        if isinstance(other, GroupMember):
            return self.index < other.index
        elif other in self.group:
            other_index = self.group.index_of(other)
            return self.index < other_index

        return self.value < other

    def __le__(self, other: typing.Union[T, GroupMember[T]]) -> bool:
        """
        Determines if this member is less than or equal to the other value

        Args:
            other: The value to compare to

        Returns:
            True if either the condition for less than or the condition for equal are true
        """
        return self < other or self == other

    def __gt__(self, other: typing.Union[T, GroupMember[T]]) -> bool:
        """
        Determines if this member is greater than the other value

        This item is considered less than the other value if:
            - The other item is a group member with a lower index
            - The other item is contained within the group and has a lower index
            - The other item is lower than the value of this member

        Examples:
            >>> group = FiniteGroup("example", [1, "two", 3, "four", 5, "six"])
            >>> member = group("four")
            >>> member > "two"
            True
            >>> member > 5
            False
            >>> member < "ninety"
            True
            >>> member > group(1)
            True
            >>> member > GroupMember(group, 3)
            False
            >>> member > GroupMember(group, 2)
            True

        Args:
            other: The value to compare to

        Returns:
            True if this index or value is greater than the value to compare to
        """
        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot compare members of two different groups")

        if isinstance(other, GroupMember):
            return self.index > other.index

        return self.value > other

    def __ge__(self, other: typing.Union[T, GroupMember[T]]) -> bool:
        """
        Determines if this member is greater than or equal to the other value

        Args:
            other: The other value to compare to

        Returns:
            True if either the condition for greater than is true or the condition for equals to is true
        """
        return self > other or self == other

    def __eq__(self, other: typing.Union[GroupMember[T], T]) -> bool:
        """
        Determines if both this member and the other member or value are equal

        Examples:
            >>> group = FiniteGroup("example", [1, "two", 3, "four", 5, "six"])
            >>> member = group("four")
            >>> member == "two"
            False
            >>> member == group(5)
            False
            >>> member == "four"
            True
            >>> member == group("four")
            True
            >>> member == GroupMember(group, 3)
            True

        Args:
            other: The other value to compare to

        Returns:
            True if the index or value are the same
        """
        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        if isinstance(other, GroupMember):
            return self.index == other.index

        return self.value == other

    def __ne__(self, other: typing.Union[GroupMember[T], T]) -> bool:
        """
        Determines if neither this member nor the other member or value are equal

        Examples:
            >>> group = FiniteGroup("example", [1, "two", 3, "four", 5, "six"])
            >>> member = group("four")
            >>> member != "two"
            True
            >>> member != group(5)
            True
            >>> member != "four"
            False
            >>> member != group("four")
            False
            >>> member != GroupMember(group, 3)
            False

        Args:
            other: The other value to compare to

        Returns:
            True if the index or value are not the same
        """
        if isinstance(other, GroupMember) and self.group != other.__group:
            raise TypeError(f"Cannot compare values from nonequivalent groups")

        if isinstance(other, GroupMember):
            return self.index == other.index

        return self.value != other

    def __isub__(self, other: typing.Union[int, GroupMember[T]]) -> Self:
        """
        Decrements the value of the other from this instance

        Args:
            other: The value or member to remove from this instance

        Returns:
            The updated instance
        """
        if not self.__other_value_is_comparable(other):
            raise TypeError(
                f"May only subtract integers or other members from a GroupMember. Received {other}: {type(other)}"
            )

        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot add members of two different groups together")

        if not isinstance(other, GroupMember):
            other = self.group.get(other)

        self.decrement(other.index)
        return self

    def __iadd__(self, other: typing.Union[int, GroupMember[T]]) -> Self:
        """
        Increments the value of the other to this instance

        Args:
            other: The value or member to add to this instance

        Returns:
            The updated instance
        """
        if not self.__other_value_is_comparable(other):
            raise TypeError(f"May only add integers or other members to a GroupMember. Received {type(other)}")

        if isinstance(other, GroupMember) and self.group != other.group:
            raise Exception(f"Cannot increment a group value by the value of another group")

        if not isinstance(other, GroupMember):
            other = self.group.get(other)

        self.increment(other.index)
        return self

    def update_by_value(self, value: T) -> Self:
        """
        Set the index of this instance to that of the value without triggering any possible rollover or rollback logic

        Args:
            value: The new value for the member

        Returns:
            The updated instance
        """
        index = self.group.index_of(value)
        self.__current_index = index
        return self

    def update_by_index(self, index: int) -> Self:
        """
        Set the index of this instance to the passed index without triggering any possible rollover or rollback logic

        Args:
            index: The new index for the member

        Returns:
            The updated instance
        """
        self.__current_index = self.group.absolute_index(index)
        return self

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return self.__str__()

    def __bool__(self):
        return self.index != 0


MemberLoopHandler = typing.Callable[Concatenate[GroupMember[T], ARGS_KWARGS], typing.Any]
"""A function that take group member along with *args and **kwargs"""
