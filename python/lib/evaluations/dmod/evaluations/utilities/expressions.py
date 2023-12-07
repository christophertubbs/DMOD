"""
@TODO: Put a module wide description here
"""
from __future__ import annotations

import dataclasses
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

DEFAULT_NEW_VARIABLE_KEY: typing.Final[str] = "variables"
"""The default key in mappings that indicate the mapped values are variables used for substitution"""

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
    r"<%\s*"
    r"'\s*(?P<value_one>[^']+)\s*'\s*"
    r":?\s*(?P<value_one_cast>(?<=:)\s*[A-aZ-z0-9_.]+)?\s*"
    r"(?P<operator>(-|\+|\*|/|\?\?|[A-Za-z0-9_.]+))\s*"
    r"'\s*(?P<value_two>[^']+)\s*'\s*"
    r":?\s*(?P<value_two_cast>(?<=:)\s*[A-aZ-z0-9_.]+)?\s*"
    r"%>"
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

WalkablePredicate = typing.Callable[
    [
        WalkableObject,
        typing.Mapping[str, typing.Any],
        typing.Union[str, int],
        typing.Any
    ],
    bool
]
"""
Represents a boolean function that investigates items from an iterable object. `f(object being walked, available variables, key or index, value)`
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


@dataclasses.dataclass
class ExtractedExpression:
    """
    A data transfer object defining the parts of an expression that may be extracted from a string
    """
    value_one: str
    value_two: str
    operator: str
    value_one_cast: typing.Optional[str] = dataclasses.field(default=None)
    value_two_cast: typing.Optional[str] = dataclasses.field(default=None)


def extract_variable_name(value: str) -> typing.Optional[str]:
    """
    Attempt to identify the name of a variable from a string

    Args:
        value: The string to investigate

    Returns:
        An identified value that might be a variable name
    """
    if not isinstance(value, str):
        return None

    matching_variable_name = VariablePattern.search(value)

    if matching_variable_name is None:
        return None

    variable_name = matching_variable_name.group("variable_name")
    variable_name = variable_name.strip()
    return variable_name


def extract_expression(value: str) -> typing.Optional[ExtractedExpression]:
    """
    Extract each member of an expression definition

    Args:
        value: The string that might contain an expression

    Returns:
        Individual members of an identified expression
    """
    if not isinstance(value, str):
        return None

    matching_expression = ExpressionPattern.search(value)

    if not matching_expression:
        return None

    value_one = matching_expression.group("value_one").strip().strip("'").strip()
    value_two = matching_expression.group("value_two").strip().strip("'").strip()
    operator = matching_expression.group("operator").strip().strip("'").strip()

    value_one_cast = matching_expression.group("value_one_cast")

    if isinstance(value_one_cast, str):
        value_one_cast = value_one_cast.strip().strip("'").strip()

    value_two_cast = matching_expression.group("value_two_cast")

    if isinstance(value_two_cast, str):
        value_two_cast = value_two_cast.strip().strip("'").strip()

    return ExtractedExpression(
        value_one=value_one,
        value_two=value_two,
        operator=operator,
        value_one_cast=value_one_cast,
        value_two_cast=value_two_cast
    )


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
        elif predicate(tree, variables, key, value):
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
        elif predicate(sequence, current_variables, index, value):
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
    """
    Convert a value into a list of values

    Args:
        value: The value to split up into a list

    Returns:
        A list of values based on what was passed in
    """
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


def evaluate_expression(
    variables: typing.Mapping[str, typing.Any],
    collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
    key_or_index: typing.Union[str, int],
    expression: str
) -> typing.Any:
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
"""Stock variable values that may be reused"""


def transform_value(
    collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
    key_or_index: typing.Union[str, int],
    predicate: WalkablePredicate,
    transformation: WalkableTransform,
    variables: typing.Mapping[str, typing.Any]
) -> int:
    """
    Apply nested transformations on identified values

    Args:
        collection:
        key_or_index:
        predicate:
        transformation:
        variables:

    Returns:

    """
    change_count = 0
    value = collection[key_or_index]

    # Store transformed values in order to keep track of conditions that indicate an infinite loop
    tracked_values = [
        value
    ]

    # The currently transformed value
    latest_value = value

    def loop_found(current_value: typing.Any = None):
        """
        Returns:
            True if
        """
        if current_value is None:
            current_value = latest_value

        return current_value in tracked_values

    # Evaluate all expressions encountered in this value.
    # This should completely evaluate values like:
    # "<% <% 13 + 5 %> + <% 8 - 2 %> %>"
    # and transform it into
    # 24
    while predicate(collection, key_or_index, latest_value) and not loop_found():
        # Run the transform function to evaluate the expression
        newly_transformed_value = transformation(
            variables,
            collection,
            key_or_index,
            latest_value
        )

        # If we've already encountered this value we'll be in an infinite loop where we're continually
        # churning out the same values. Fail immediately to prevent a locking operation
        if loop_found(newly_transformed_value):
            raise ValueError(
                f'Failed to correctly evaluate an expression - "{tracked_values[0]}" with the key "{key_or_index}" '
                f'might cause an infinite loop'
            )

        # Add the transformed value for loop tracking
        tracked_values.append(newly_transformed_value)
        latest_value = newly_transformed_value

        # Assign the new value to the dataset
        collection[key_or_index] = latest_value
        change_count += 1

    return change_count


def create_variables_for_use(
    data: typing.MutableMapping,
    variables: typing.Mapping[str, typing.Any],
    new_variable_key: str = None
) -> typing.Tuple[typing.MutableMapping[str, typing.Any], bool]:
    """
    Creates a new collection of variables to use for substitution based on previous data and potentially new data

    Args:
        data: The collection that may or may not hold new variable definitions
        variables: Previously existing variable data
        new_variable_key: The key that indicates a member in the collection that holds new variables

    Returns:
        A new map of usable variables and whether new variables were introduced
    """
    if new_variable_key is None:
        new_variable_key = DEFAULT_NEW_VARIABLE_KEY

    if not isinstance(variables, typing.Mapping):
        variables = {}

    if new_variable_key in data:
        variables_to_use = {
            key: value
            for key, value in data.get(new_variable_key, {}).items()
        }
        has_new_variables = len(variables_to_use) > 0
    else:
        variables_to_use = {}
        has_new_variables = False

    variables_to_use.update({
        key: value
        for key, value in variables
        if key not in variables_to_use
    })

    return variables_to_use, has_new_variables


def should_replace_variable(
    collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
    variables: typing.Mapping[str, typing.Any],
    key_or_index: typing.Union[str, int],
    encountered_value: _CombinedStaticVariableType
) -> bool:
    """
    Determines whether a value declares that there is a value that should be replaced with a variable

    Args:
        collection: That collection that contains the current value
        key_or_index: The key of the current value
        encountered_value: The current value to check
        variables: A collection of currently available variables

    Returns:
        True if the value needs to be transformed
    """
    if not variables:
        raise ValueError(f"Cannot determine if a variable use should be replaced - no variables were passed")

    # A value that isn't a string can't hold a variable, so move on if it's not one
    if not isinstance(encountered_value, str):
        return False

    # Try to find a value matching the variable pattern
    try:
        variable_match = VariablePattern.search(encountered_value)
    except TypeError as error:
        logging.error(f"Could not search for a variable in {encountered_value}; {error}")
        raise

    # If nothing was found, declare that a replacement isn't needed
    if not variable_match:
        return False

    # Check to see if a variable by the given name even exists
    variable_name: str = variable_match.group("variable_name")
    variable_name = variable_name.strip()

    return variable_name in variables or variable_name in CONSTANT_VARIABLE_VALUES


def apply_variable(
    current_variables: typing.Mapping[str, StaticVariableType],
    collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
    key_or_index: typing.Union[str, int],
    encountered_value: _CombinedStaticVariableType
) -> typing.Any:
    """
    Replace the current value with an available replacement

    Args:
        current_variables: The collection of defined variables available for use
        collection: The collection that the encountered values came from
        key_or_index: The sequential index or map key of the encountered value
        encountered_value: The value to be transformed

    Returns:
        A new value containing the replacement for the indicated variable
    """
    variable_name: str = VariablePattern.search(encountered_value).group("variable_name").strip()

    if variable_name in current_variables:
        replacement = current_variables[variable_name]
    elif variable_name in CONSTANT_VARIABLE_VALUES:
        replacement = CONSTANT_VARIABLE_VALUES[variable_name]
    else:
        return encountered_value

    if isinstance(replacement, typing.Callable):
        replacement = replacement()

    with_variable_name_pattern = r"\{\{%\s*" + variable_name + r"\s*%}}"
    value_without_variable = re.sub(with_variable_name_pattern, "", encountered_value)

    if len(value_without_variable) > 0:
        replacement = re.sub(with_variable_name_pattern, str(replacement), encountered_value)
        replacement = replacement.strip()

    return replacement


def search_for_and_apply_variables(
    data: typing.MutableMapping,
    variables: typing.Mapping[str, typing.Any] = None,
    new_variable_key: str = None
) -> int:
    """
    Looks for and replace values with specified variable values

    Args:
        data: The tree to iterate over
        variables: A collection of variables used to replace found values
        new_variable_key: A key that indicates that a member of the data contains more variable definitions

    Returns:
        The number of values replaced
    """
    if new_variable_key is None:
        new_variable_key = DEFAULT_NEW_VARIABLE_KEY

    variables_to_use, has_new_variables = create_variables_for_use(
        data=data,
        variables=variables,
        new_variable_key=new_variable_key
    )

    change_count = 0

    # Iterate over each key and value to find values to investigate and nested structures to further walk
    for key, value in data.items():
        # If new variables were encountered and we're on the key that gave them to us, we can go ahead and skip this
        # step
        if has_new_variables and key == new_variable_key:
            continue

        # If we've hit another tree, we want to walk it to find more variables to replace
        if isinstance(value, typing.MutableMapping):
            change_count += transform_tree(
                tree=value,
                predicate=should_replace_variable,
                transformation=apply_variable,
                current_variables=variables_to_use,
                new_variable_key=new_variable_key
            )
        elif not isinstance(value, (str, bytes, typing.Mapping)) and isinstance(value, typing.MutableSequence):
            change_count += transform_sequence(
                sequence=value,
                predicate=should_replace_variable,
                transformation=apply_variable,
                current_variables=variables_to_use,
                new_variable_key=new_variable_key
            )
        elif should_replace_variable(collection=data, key_or_index=key, encountered_value=value):
            change_count += transform_value(
                collection=data,
                key_or_index=key,
                predicate=should_replace_variable,
                transformation=apply_variable,
                variables=variables_to_use
            )

    return change_count


def is_expression(
    collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
    variables: typing.Mapping,
    key_or_index: typing.Union[str, int],
    encountered_value: _CombinedStaticVariableType
) -> bool:
    """
    Determines if an encountered value contains an expression that needs to be evaluated

    Args:
        collection: The original collection that has the value that might be an expression
        variables: Variables that are available for use
        key_or_index: The map key or sequence index of the encountered value
        encountered_value: The value to check

    Returns:
        True if the encountered value is a string that contains an expression
    """
    if not isinstance(encountered_value, str):
        return False

    return ExpressionPattern.search(encountered_value) is not None


def search_for_and_apply_expressions(
    data: typing.MutableMapping,
    variables: typing.Mapping = None,
    new_variable_key: str = None
) -> int:
    """
    Looks for and evaluates found expressions within a tree

    Args:
        data: The tree to iterate over
        variables: A collection of variables used to replace found values
        new_variable_key: A key that indicates that a member of the data contains more variable definitions

    Returns:
        The number of expressions evaluated
    """
    if new_variable_key is None:
        new_variable_key = DEFAULT_NEW_VARIABLE_KEY

    variables_to_use, has_new_variables = create_variables_for_use(
        data=data,
        variables=variables,
        new_variable_key=new_variable_key
    )

    change_count = 0

    # Iterate over each key and value to find values to investigate and nested structures to further walk
    for key, value in data.items():
        # If new variables were encountered and we're on the key that gave them to us, we can go ahead and skip this
        # step
        if has_new_variables and key == new_variable_key:
            continue

        # If we've hit another tree, we want to walk it to find more values to operate on
        if isinstance(value, typing.MutableMapping):
            change_count += transform_tree(
                tree=value,
                predicate=is_expression,
                transformation=evaluate_expression,
                current_variables=variables_to_use,
                new_variable_key=new_variable_key
            )
        elif not isinstance(value, (str, bytes, typing.Mapping)) and isinstance(value, typing.MutableSequence):
            change_count += transform_sequence(
                sequence=value,
                predicate=is_expression,
                transformation=evaluate_expression,
                current_variables=variables_to_use,
                new_variable_key=new_variable_key
            )
        elif is_expression(collection=data, variables=variables_to_use, key_or_index=key, encountered_value=value):
            change_count += transform_value(
                collection=data,
                key_or_index=key,
                predicate=is_expression,
                transformation=evaluate_expression,
                variables=variables_to_use
            )

    return change_count


def process_expressions(data: typing.MutableMapping, variables: typing.Mapping, iterations: int = None) -> int:
    """
    Searches for and applies variable values and evaluates expressions several times to ensure that
    nested and changed variables and expressions are correctly evaluated

    Args:
        data: The initial tree to run expressions upon
        variables: Variables that may be used to set values
        iterations: The number of times that

    Returns:
        The total number of changes that were applied
    """
    if iterations is None:
        iterations = DEFAULT_PROCESS_ITERATION_COUNT

    total_change_count = 0

    for _ in range(iterations):
        change_count = search_for_and_apply_variables(data=data, variables=variables)
        change_count += search_for_and_apply_expressions(data=data, variables=variables)
        total_change_count += change_count

        if change_count == 0:
            break

    return total_change_count