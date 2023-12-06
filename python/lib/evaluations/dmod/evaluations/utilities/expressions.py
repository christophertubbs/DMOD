"""
@TODO: Put a module wide description here
"""
from __future__ import annotations

import json
import logging
import pathlib
import typing
import re
import importlib

from datetime import datetime
from datetime import timezone

from dateutil.parser import parse as parse_date
from typing_extensions import ParamSpec

from dmod.core.common import find

ARGS_AND_KWARGS = ParamSpec("ARGS_AND_KWARGS")
"""A type variable indicating *args and **kwargs when defining types like callables"""

_RawStaticVariableType = typing.Union[
    float,
    int,
    str
]
"""Raw value types for static variables"""


_CollectionOfStaticVariableType = typing.Union[
    typing.List[_RawStaticVariableType],
    typing.Dict[str, _RawStaticVariableType]
]
"""Collection types for the raw variable types used for static expressions"""

_CombinedStaticVariableType = typing.Union[
    _RawStaticVariableType,
    _CollectionOfStaticVariableType,
    typing.List[_CollectionOfStaticVariableType],
    typing.Dict[str, _CollectionOfStaticVariableType]
]
"""The full set of types that may be used for static variable expressions"""

StaticVariableType = typing.Union[
    typing.Callable[[ARGS_AND_KWARGS], _CombinedStaticVariableType],
    _CombinedStaticVariableType
]
"""
A Type that is either a type of static variable value or a function with an arbitrary number of parameters 
that produces a static variable value
"""

DEFAULT_PROCESS_ITERATION_COUNT: typing.Final[int] = 5
"""
The default number of times a collection of input data should have expressions and variables evaluated

Iterative interpretation allows expressions and variables to have iterative results, meaning that an expression may 
yield a variable name that needs processing that yields an expression that needs processing. Iterations are limited 
to artificially prevent infinite loops.
"""

VariablePattern = re.compile(
    r"\s*(?<=\{\{%)(?P<variable_name>\s*[-a-zA-Z0-9_\\+]+(\s*[-a-zA-Z0-9_\\+]+)*\s*?)(?=%}})\s*"
)
"""
A pattern that shows that an identified variable COULD replace the captured `variable_name` group

Examples:
    >>> VariablePattern.search("{{% example %}}") is not None
    True
    >>> VariablePattern.search("{{% this Is a Variable Name %}}") is not None
    True
    >>> VariablePattern.search("{{%value %}}") is not None
    True
    >>> VariablePattern.search("{{% root %}}/path") is not None
    True
"""

ExpressionPattern = re.compile(
    r"(?<=<%)\s*"
    r"'(?P<value_one>\[?[-a-zA-Z0-9_\\+.]+(,?\s*[-a-zA-Z0-9_\\+]+)*]?)'\s*"
    r":?\s*(?P<value_one_cast>(?<=:)[A-aZ-z0-9_]+)?\s*"
    r"(?P<operator>(-|\+|\*|/|get|\?\?|'[A-Za-z0-9_.]+'))\s*"
    r"'(?P<value_two>\[?[a-zA-Z0-9_\\+.-]+(,?\s*[a-zA-Z0-9_\\+.-]+)*]?)'\s*"
    r":?\s*(?P<value_two_cast>[A-aZ-z0-9_.]+)?\s*"
    r"(?=%>)"
)
"""
A pattern revealing an operation to perform on two values.

There are 5 elements:
1. The first value or the name of a variable for the first value
2. An optional cast of the first variable
3. The operation to be performed
4. The second value or name of a variable for the second value
5. An optional cast of the second variable

Examples:
    >>> # Add the value of that `some variable name` static variable to the `some other variable name` static variable
    >>> ExpressionPattern.search("<% 'some variable name' + 'some other variable name' %>")
    True
    >>> # Subtract 5 from the value of the `variable name` static variable
    >>> ExpressionPattern.search("<% 'variable name' - '5' %>")
    True
    >>> # Get the value in index 2 of ['one', 'two', 'three']
    >>> ExpressionPattern.search("<% 'one two three': list get '2' %>")
    True
    >>> # Get every other value from index 0 up to index 6 from ['one', 'two', 'three', 'four', 'five']
    >>> ExpressionPattern.search("<% 'one two three four five' get '0 6 2': slice %>")
    True
"""


WalkableObject = typing.Union[typing.MutableSequence, typing.MutableMapping[str, typing.Any]]
"""Represents an object that may be iterated over"""

WalkablePredicate = typing.Callable[[WalkableObject, typing.Union[str, int], typing.Any], bool]
"""
Represents a boolean function that investigates items from an iterable object. `f(object being walked, key or index, value)`
"""

WalkableTransform = typing.Callable[
    [
        typing.Mapping[str, typing.Any],
        WalkableObject,
        typing.Union[str, int],
        typing.Any
    ],
    typing.Any
]
"""
Represents a function that may transform a value from an iterable object. `f(variables, object being walked, key or index, value)`

Parameters:
    1. A mapping of variables that may be subbed into identified values
    2. The object being iterated over
    3. The key or index of the object being iterated over
    4. The value encountered in the iterable object at the given key or index
"""


class AvailableModules:
    """
    Reveals modules where extra code may be utilized.

    Restricts what code may or may not be called from an expression
    """
    collections: importlib.import_module("collections")
    """The vanilla `collections` library"""

    _invalid_paths = (
        "collections.abc",
        'requests',
    )
    """Object paths that are not authorized for use"""

    @classmethod
    def call(cls, path: str, *args) -> typing.Any:
        """
        Call a function found at the given path

        Args:
            path: Where to find the function to call
            *args: Arguments for the function

        Returns:
            The results of the function
        """
        function = cls.get(path=path, validate_type=typing.Callable)
        return function(*args)

    @classmethod
    def get(cls, path: str, *, validate_type: typing.Type = None):
        """
        Get an object from the path from the set of approved modules

        Args:
            path: The path to the object
            validate_type: A type of object to compare the result to - an error is thrown if the retrieved object is not of this type

        Returns:
            The object found at the path
        """
        if path.startswith("_invalid_paths"):
            raise KeyError(f"'_invalid_paths' is an internal member and may not be accessed")

        invalid_path = find(cls._invalid_paths, lambda unauthorized_path: path.startswith(unauthorized_path))

        if invalid_path is not None:
            raise KeyError(f"Objects and functions from '{invalid_path}' are not allowed")

        name_parts = path.split(".")

        if hasattr(cls, name_parts[0]):
            element = getattr(cls, name_parts[0])
            found_element_name = name_parts[0]

            for part in name_parts[1:]:
                if hasattr(element, part):
                    element = getattr(element, part)
                    found_element_name += f".{part}"
                else:
                    raise KeyError(f"Cannot find a dynamic element - nothing is available at the full path from {path}")
        else:
            raise KeyError(f"There are no available modules named {name_parts[0]}")

        if validate_type is not None and not isinstance(element, validate_type):
            raise TypeError(f"The item found at {found_element_name} is not the expected type {validate_type}")

        return element


def transform_tree(
    tree: typing.MutableMapping[str, typing.Any],
    predicate: WalkablePredicate,
    transformation: WalkableTransform,
    current_variables: typing.Mapping[str, typing.Any] = None,
    new_variable_key: str = None
) -> int:
    """
    Walk a tree and mutate all values that fit the predicate in place

    Args:
        tree: The tree structure to walk
        predicate: A function that determines if the transformation should be applied
        transformation: A function that transforms identified values
        current_variables: Variables that may be built up during the walking process
        new_variable_key: A key for a member that may contain more variables

    Returns:
        The number of values that were mutated
    """
    # Get any defined variables for this level of the tree
    defined_variables = tree.get(new_variable_key, {})
    has_defined_variables = isinstance(defined_variables, typing.Mapping)

    # If the found variables is a mapping, we can use those values
    if isinstance(defined_variables, typing.Mapping):
        # Copy all values within the current level of the tree that define static variables to insert into variable
        # references
        variables = {
            key: value
            for key, value in tree.get(new_variable_key, {})
        }
    else:
        # Ignore the value if the identified variables value isn't a mapping
        variables = {}

    # Add previously identified variable definitions without overriding variables defined on this level of the tree
    variables.update({
        key: value
        for key, value in (current_variables or {}).items()
        if key not in variables
    })

    change_count = 0

    # Iterate over each key-value pair to ensure that any nested trees are walked and that all members are
    # considered for transformation
    for key, value in tree.items():
        # If variables were defined on this level of the tree, ignore the key pointing to them so the definitions
        # don't get overridden
        if has_defined_variables and key == new_variable_key:
            continue

        # We want to continue to climb the tree if a nested tree is found
        if isinstance(value, typing.MutableMapping):
            change_count += transform_tree(
                tree=value,
                predicate=predicate,
                transformation=transformation,
                current_variables=variables,
                new_variable_key=new_variable_key
            )
        elif not isinstance(value, (str, bytes, typing.Mapping)) and isinstance(value, typing.MutableSequence):
            # If a collection of values was identified, we want to iterate through each value to determine what values
            # (if any) within the collection should be modified. This continues the walking to ensure that lists of
            # nested trees are correctly processed
            change_count += transform_sequence(
                sequence=value,
                predicate=predicate,
                transformation=transformation,
                current_variables=variables,
                new_variable_key=new_variable_key
            )
        elif predicate(tree, key, value):
            # If the predicate determines that the encountered value should be modified, transform the value
            transformed_value = transformation(variables, tree, key, value)

            # We can consider the value altered if it isn't equivalent to the previous value
            if tree[key] != transformed_value:
                tree[key] = transformation(variables, tree, key, value)
                change_count += 1

    return change_count


def transform_sequence(
    sequence: typing.MutableSequence[typing.Any],
    predicate: WalkablePredicate,
    transformation: WalkableTransform,
    current_variables: typing.Mapping[str, typing.Any] = None,
    new_variable_key: str = None
) -> int:
    """
    Walk a list and mutate all values that fit the predicate in place

    Args:
        sequence: The list to walk
        predicate: A function that determines if the transformation should be applied
        transformation: A function that transforms the value
        current_variables: Variables that may be built up during the walking process
        new_variable_key: A key for a member that may contain more variables

    Returns:
        The number of transformed values
    """

    change_count = 0

    # Iterate over each value in the sequence to ensure that the structure is correctly walked and considered
    for index, value in enumerate(sequence):
        # We want to walk through and transform any nested mappings
        if isinstance(value, typing.MutableMapping):
            change_count += transform_tree(
                tree=value,
                predicate=predicate,
                transformation=transformation,
                current_variables=current_variables,
                new_variable_key=new_variable_key
            )
        elif isinstance(value, typing.MutableSequence):
            # We want to walk any nested list just like what we're doing now
            change_count += transform_sequence(
                sequence=value,
                predicate=predicate,
                transformation=transformation,
                current_variables=current_variables,
                new_variable_key=new_variable_key
            )
        elif predicate(sequence, index, value):
            # If the predicate determines that the encountered value should be modified, transform the value
            transformed_value = transformation(current_variables, sequence, index, value)

            # We can consider the value altered if it isn't equivalent to the previous value
            if transformed_value != value:
                sequence[index] = transformation(current_variables, sequence, index, value)
                change_count += 1

    return change_count


ExpressionOperator: typing.Final[typing.Mapping[str, typing.Callable[[typing.Any, typing.Any], typing.Any]]] = {
    "+": lambda value_one, value_two: value_one + value_two,
    "-": lambda value_one, value_two: value_one - value_two,
    "*": lambda value_one, value_two: value_one * value_two,
    "/": lambda value_one, value_two: value_one / value_two,
    "get": lambda value_one, value_two: value_one[value_two],
    "??": lambda value_one, value_two: value_one if value_one is not None else value_two
}
"""
Predetermined strings indicating stock functions that may be performed within expressions
"""


def perform_operation(value_one, operation: str, value_two) -> typing.Any:
    """
    Perform the function specified by `operation` on `value_one` and `value_two`

    This assumes that `value_one` and `value_two` were already cast into the right types

    Given the expression `<% '9' + '8.5' %>`, `value_one` is `9`, `value_two` is `8.5`, and the operation is `+`

    Args:
        value_one: The first participant of the operation
        operation: The name of the operation to perform
        value_two: The second participant of the operation to perform

    Returns:
        The result of the operation
    """
    # If the definition of the operation is in the ExpressionOperator, just call that function since it is
    # specially set up for it
    if operation in ExpressionOperator:
        return ExpressionOperator[operation](value_one, value_two)

    # If the operation is a member of one of the values, call that member function with the other value
    if hasattr(value_one, operation):
        return getattr(value_one, operation)(value_two)
    elif hasattr(value_two, operation):
        return getattr(value_two, operation)(value_one)

    # If the operator STILL hasn't been found, try to get it from the AvailableModules
    operator = AvailableModules.get(operation)

    if isinstance(operator, typing.Callable):
        # Try to call the function with the values one and two as the arguments
        #   There are a ton of ways this could go wrong, so the fact that it can fail needs to be accepted and it
        #   needs to be properly logged when failing
        try:
            return operator(value_one, value_two)
        except BaseException as operation_exception:
            raise Exception(
                f"The operation '{operation}' failed with the parameters '{value_one}' and '{value_two}' - "
                f"{operation_exception}"
            ) from operation_exception
    else:
        # No operation could be found, so report it and fail
        raise TypeError(
            f"Cannot perform the operation named '{operation}' on {value_one} and {value_two} - it is not a function"
        )


def value_to_sequence(value) -> typing.Sequence:
    if isinstance(value, typing.Sequence) and not isinstance(value, (str, bytes, typing.Mapping)):
        return value

    if isinstance(value, str) and "|" in value:
        return value.split("|")
    elif isinstance(value, str) and "," in value:
        return value.split(",")

    return [value]


def to_slice(value) -> slice:
    """
    Convert a set of received values into a slice that may be used for data gathering

    Args:
        value: A set of values that may be a sequence of values

    Returns:
        A slice object
    """
    # Try to convert the found value into a sequence
    value = [int(float(val)) for val in value_to_sequence(value)]

    # If the length of the generated sequence is 3 or more, we can generate a slice with a start, stop and step
    if len(value) >= 3:
        return slice(value[0], value[1], value[2])
    elif len(value) == 2:
        # If only two values are available, we can create a slice with a start and stop
        return slice(value[0], value[1])

    # If only one value is available, we can only create a slice with a stopping point
    return slice(value[0])


CastOperation: typing.Mapping[str, typing.Callable[[typing.Any], typing.Any]] = {
    "list": value_to_sequence,
    "slice": to_slice,
    "set": lambda value: set(value_to_sequence(value)),
    "int": lambda value: int(float(value)) if isinstance(value, str) else int(value),
    "integer": lambda value: int(float(value)) if isinstance(value, str) else int(value),
    "float": float,
    "number": float,
    "str": str,
    "string": str,
    "date": lambda value: value if isinstance(value, datetime) else parse_date(value),
    "datetime": lambda value: value if isinstance(value, datetime) else parse_date(value),
    "dict": lambda value: value if isinstance(value, typing.Mapping) else json.loads(value),
    "map": lambda value: value if isinstance(value, typing.Mapping) else json.loads(value),
    "path": pathlib.Path
}
"""
Hardcoded names for types that values may be cast as

    >>> "<% 1992-05-22 05:00: datetime operator other value%>"
    
will result in the value "1992-05-22 05:00" getting converted into a datetime-like object using 
`CastOperation['datetime'](value)`
"""


def cast_value(value, cast_name: str = None) -> typing.Any:
    """
    Convert a value into a desired type. If the cast is not defined within the stock types `globals`
    is searched for a matching operation.

    Args:
        value: The value to convert
        cast_name: The name of the type that the value should be converted to

    Returns:
        The converted value
    """
    if cast_name is None:
        return value

    cast_name = cast_name.strip()

    if cast_name in CastOperation:
        try:
            return CastOperation[cast_name](value)
        except BaseException as exception:
            raise TypeError(
                f"Could not perform the '{cast_name}' casting operation on the value '{value}'"
            ) from exception

    return AvailableModules.call(cast_name, value)


def evaluate_expression(variables: typing.Mapping[str, typing.Any], expression: str) -> typing.Any:
    identified_expression_parts = ExpressionPattern.search(expression)

    if identified_expression_parts is None:
        return expression

    value_one = identified_expression_parts.group("value_one").strip()
    value_two = identified_expression_parts.group("value_two").strip()
    operation = identified_expression_parts.group("operator").strip()

    value_one = variables.get(value_one, value_one)
    value_two = variables.get(value_two, value_two)

    value_one = cast_value(value_one, identified_expression_parts.group("value_one_cast"))
    value_two = cast_value(value_two, identified_expression_parts.group("value_two_cast"))

    value_one_variable_keys = list()
    while value_one in variables and value_one not in value_one_variable_keys:
        value_one_variable_keys.append(value_one)
        value_one = variables[value_one]

    value_two_variable_keys = list()
    while value_two in variables and value_two not in value_two_variable_keys:
        value_two_variable_keys.append(value_two)
        value_two = variables[value_two]

    evaluated_expression = perform_operation(value_one=value_one, operation=operation, value_two=value_two)
    return evaluated_expression


CONSTANT_VARIABLE_VALUES: typing.Mapping[str, StaticVariableType] = {
    "NOW NAIVE": lambda *args, **kwargs: datetime.now().strftime("%Y-%m-%dT%H:%M"),
    "NOW UTC": lambda *args, **kwargs: datetime.now().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M%z"),
    "NOW": lambda *args, **kwargs: datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M%z"),
    "NULL": None
}


def search_for_and_apply_variables(data: typing.MutableMapping, variables: typing.Mapping[str, typing.Any]) -> int:
    def should_replace_variable(
        collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
        key_or_index: typing.Union[str, int],
        encountered_value: _CombinedStaticVariableType
    ) -> bool:
        if not isinstance(encountered_value, str):
            return False

        try:
            variable_match = VariablePattern.search(encountered_value)
        except TypeError as error:
            logging.error(f"Could not search for a variable in {encountered_value}; {error}")
            raise

        if not variable_match:
            return False

        variable_name: str = variable_match.group("variable_name")
        variable_name = variable_name.strip()

        return variable_name in variables or variable_name in CONSTANT_VARIABLE_VALUES

    def apply_variable(
        current_variables: typing.Mapping[str, StaticVariableType],
        collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
        key_or_index: typing.Union[str, int],
        encountered_value: _CombinedStaticVariableType
    ) -> typing.Any:
        variable_name: str = VariablePattern.search(encountered_value).group("variable_name").strip()

        if variable_name in current_variables:
            replacement = current_variables[variable_name]
        elif variable_name in CONSTANT_VARIABLE_VALUES:
            replacement = CONSTANT_VARIABLE_VALUES[variable_name]
        else:
            return encountered_value

        if isinstance(replacement, typing.Callable):
            replacement = replacement()

        with_variable_name_pattern = r"\s*\{\{%\s*" + variable_name + r"\s*%}}"
        value_without_variable = re.sub(with_variable_name_pattern, "", encountered_value)

        if len(value_without_variable) > 0:
            replacement = re.sub(with_variable_name_pattern, str(replacement), encountered_value)

        return replacement

    change_count = 0
    for key, value in data.items():
        if key == 'variables':
            continue

        if isinstance(value, typing.MutableMapping):
            change_count += transform_tree(
                tree=value,
                predicate=should_replace_variable,
                transformation=apply_variable,
                current_variables=variables,
                new_variable_key='variables'
            )
        elif not isinstance(value, (str, bytes, typing.Mapping)) and isinstance(value, typing.MutableSequence):
            change_count += transform_sequence(
                sequence=value,
                predicate=should_replace_variable,
                transformation=apply_variable,
                current_variables=variables,
                new_variable_key='variables'
            )
        elif should_replace_variable(collection=data, key_or_index=key, encountered_value=value):
            transformed_value = apply_variable(
                current_variables=variables,
                collection=data,
                key_or_index=key,
                encountered_value=value
            )

            if transformed_value != value:
                data[key] = transformed_value
                change_count += 1

    return change_count


def search_for_and_apply_expressions(data: typing.MutableMapping, variables: typing.Mapping) -> int:
    def is_expression(
        collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
        key_or_index: typing.Union[str, int],
        encountered_value: _CombinedStaticVariableType
    ) -> bool:
        if not isinstance(encountered_value, str):
            return False

        return ExpressionPattern.search(encountered_value) is not None

    def apply_expression(
        current_variables: typing.Mapping[str, StaticVariableType],
        collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
        key_or_index: typing.Union[str, int],
        encountered_value: _CombinedStaticVariableType
    ) -> typing.Any:
        return evaluate_expression(current_variables, encountered_value)

    change_count = 0
    for key, value in data.items():
        if key == 'variables':
            continue

        if isinstance(value, typing.MutableMapping):
            change_count += transform_tree(
                tree=value,
                predicate=is_expression,
                transformation=apply_expression,
                current_variables=variables,
                new_variable_key='variables'
            )
        elif not isinstance(value, (str, bytes, typing.Mapping)) and isinstance(value, typing.MutableSequence):
            change_count += transform_sequence(
                sequence=value,
                predicate=is_expression,
                transformation=apply_expression,
                current_variables=variables,
                new_variable_key='variables'
            )
        elif is_expression(collection=data, key_or_index=key, encountered_value=value):
            transformed_value = apply_expression(
                current_variables=variables,
                collection=data,
                key_or_index=key,
                encountered_value=value
            )
            if transformed_value != value:
                data[key] = transformed_value
                change_count += 1
    return change_count


def process_expressions(data: typing.MutableMapping, variables: typing.Mapping, iterations: int = None):
    if iterations is None:
        iterations = DEFAULT_PROCESS_ITERATION_COUNT

    for _ in range(iterations):
        change_count = search_for_and_apply_variables(data=data, variables=variables)
        change_count += search_for_and_apply_expressions(data=data, variables=variables)

        if change_count == 0:
            break