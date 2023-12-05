"""
@TODO: Put a module wide description here
"""
from __future__ import annotations

import json
import logging
import typing
import re

from datetime import datetime
from datetime import timezone

from dateutil.parser import parse as parse_date
from typing_extensions import ParamSpec

ARGS_AND_KWARGS = ParamSpec("ARGS_AND_KWARGS")

RawExpressionVariableType = typing.Union[
    float,
    int,
    str
]
"""Raw value types for static variables"""


CollectionOfExpressionVariableType = typing.Union[
    typing.List[RawExpressionVariableType],
    typing.Dict[str, RawExpressionVariableType]
]
"""Collection types for the raw variable types used for static expressions"""

ExpressionVariableType = typing.Union[
    RawExpressionVariableType,
    CollectionOfExpressionVariableType,
    typing.List[CollectionOfExpressionVariableType],
    typing.Dict[str, CollectionOfExpressionVariableType]
]
"""The full set of types that may be used for static variable expressions"""

VariableType = typing.Union[typing.Callable[[ARGS_AND_KWARGS], ExpressionVariableType], ExpressionVariableType]

DEFAULT_PROCESS_ITERATION_COUNT: typing.Final[int] = 5

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
    r"\s*(?<=<%)"
    r"(?P<value_one>\s*[-a-zA-Z0-9_\\+]+(\s*[-a-zA-Z0-9_\\+]+)*\s*?):?"
    r"(?P<value_one_cast>\s*[A-aZ-z0-9_]+\s*)?"
    r"(?P<operator>(-|\+|\*|/|get|\?\?|[A-Za-z0-9_]+))"
    r"(?P<value_two>\s*[-a-zA-Z0-9_\\+]+(\s*[-a-zA-Z0-9_\\+]+)*\s*?):?"
    r"(?P<value_two_cast>\s*[A-aZ-z0-9_]+\s*)?"
    r"(?=%>)\s*"
)
"""
A pattern revealing an operation to perform on two values.

There are 5 elements:
1. The first value or the name of a variable for the first value
2. An optional cast of the first variable
3. The operation to be performed
4. 

Examples:
    >>> ExpressionPattern.search("<% some variable name + some other variable name %>")
    True
    >>> ExpressionPattern.search("<% variable name - 5 %>")
    True
    >>> ExpressionPattern.search("<% one two three: list get 2 %>")
    True
    >>> ExpressionPattern.search("<% one two three four five get 0 6 2: slice %>")
    True
"""


WalkableObject = typing.Union[typing.MutableSequence, typing.MutableMapping[str, typing.Any]]
WalkablePredicate = typing.Callable[[WalkableObject, typing.Union[str, int], typing.Any], bool]
WalkableTransform = typing.Callable[
    [
        typing.Mapping[str, typing.Any],
        WalkableObject,
        typing.Union[str, int],
        typing.Any
    ],
    typing.Any
]


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
        tree: The tree to walk
        predicate: A function, taking the key/numeric index and value, that determines if the transformation should be applied
        transformation: A function, taking the key/numeric index and value, that transforms the value
        current_variables: Variables that may be built up during the walking process
        new_variable_key: A key for a member that may contain more variables
    """

    variables = {
        key: value
        for key, value in tree.get(new_variable_key, {})
    }

    variables.update({
        key: value
        for key, value in (current_variables or {}).items()
        if key not in variables
    })

    change_count = 0
    for key, value in tree.items():
        if isinstance(value, typing.MutableMapping):
            change_count += transform_tree(
                tree=value,
                predicate=predicate,
                transformation=transformation,
                current_variables=variables,
                new_variable_key=new_variable_key
            )
        elif not isinstance(value, (str, bytes, typing.Mapping)) and isinstance(value, typing.MutableSequence):
            change_count += transform_sequence(
                sequence=value,
                predicate=predicate,
                transformation=transformation,
                current_variables=variables,
                new_variable_key=new_variable_key
            )
        elif predicate(tree, key, value):
            transformed_value = transformation(variables, tree, key, value)

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
        predicate: A function, taking the key/numeric index and value, that determines if the transformation should be applied
        transformation: A function, taking the key/numeric index and value, that transforms the value
        current_variables: Variables that may be built up during the walking process
        new_variable_key: A key for a member that may contain more variables
    """

    change_count = 0
    for index, value in enumerate(sequence):
        if isinstance(value, typing.MutableMapping):
            change_count += transform_tree(
                tree=value,
                predicate=predicate,
                transformation=transformation,
                current_variables=current_variables,
                new_variable_key=new_variable_key
            )
        elif isinstance(value, typing.MutableSequence):
            change_count += transform_sequence(
                sequence=value,
                predicate=predicate,
                transformation=transformation,
                current_variables=current_variables,
                new_variable_key=new_variable_key
            )
        elif predicate(sequence, index, value):
            transformed_value = transformation(current_variables, sequence, index, value)

            if transformed_value != value:
                sequence[index] = transformation(current_variables, sequence, index, value)
                change_count += 1

    return change_count


ExpressionOperator = {
    "+": lambda value_one, value_two: value_one + value_two,
    "-": lambda value_one, value_two: value_one - value_two,
    "*": lambda value_one, value_two: value_one * value_two,
    "/": lambda value_one, value_two: value_one / value_two,
    "get": lambda value_one, value_two: value_one[value_two],
    "??": lambda value_one, value_two: value_one if value_one is not None else value_two
}


def perform_operation(value_one, operation: str, value_two) -> typing.Any:
    if operation in ExpressionOperator:
        return ExpressionOperator[operation](value_one, value_two)

    if not hasattr(value_one, operation) and not hasattr(value_two, operation):
        raise ValueError(
            f"Cannot perform '{value_one}: {type(value_one)} {operation} {value_two}: {type(value_two)}' "
            f"- no operation named '{operation}' could be found on either '{value_one}' or '{value_two}'")

    if hasattr(value_one, operation):
        return getattr(value_one, operation)(value_two)

    return getattr(value_two, operation)(value_one)


def value_to_sequence(value) -> typing.Sequence:
    if isinstance(value, typing.Sequence) and not isinstance(value, (str, bytes, typing.Mapping)):
        return value

    if isinstance(value, str) and " " in value:
        return value.split(" ")
    elif isinstance(value, str) and "|" in value:
        return value.split("|")
    elif isinstance(value, str) and "," in value:
        return value.split(",")

    return [value]


def to_slice(value) -> slice:
    value = value_to_sequence(value)

    if len(value) >= 3:
        return slice(value[0], value[1], value[2])
    elif len(value) == 2:
        return slice(value[0], value[1])

    return slice(value[0])


CastOperation = {
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
    "map": lambda value: value if isinstance(value, typing.Mapping) else json.loads(value)
}


def cast_value(value, cast_name: str) -> typing.Any:
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

    cast_name_parts = cast_name.split(".")

    root = globals().get(cast_name_parts[0])

    if root is not None:
        function = root
        function_name = cast_name_parts[0]
        for part in cast_name_parts[1:]:
            if not hasattr(function, part):
                break
            function = getattr(function, part)
            function_name += f".{part}"

        if isinstance(function, typing.Callable):
            try:
                value = function(value)
            except BaseException as exception:
                raise Exception(
                    f"Could not cast the value '{value}' with the function '{function_name}'"
                ) from exception
        else:
            raise Exception(
                f"Could not cast the value '{value}' with the instruction '{function_name}' - it is not callable"
            )

    return value


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


CONSTANT_VARIABLE_VALUES: typing.Mapping[str, VariableType] = {
    "NOW NAIVE": lambda *args, **kwargs: datetime.now().strftime("%Y-%m-%dT%H:%M"),
    "NOW UTC": lambda *args, **kwargs: datetime.now().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M%z"),
    "NOW": lambda *args, **kwargs: datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M%z"),
    "NULL": None
}


def search_for_and_apply_variables(data: typing.MutableMapping, variables: typing.Mapping[str, typing.Any]) -> int:
    def should_replace_variable(
        collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
        key_or_index: typing.Union[str, int],
        encountered_value: ExpressionVariableType
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
        current_variables: typing.Mapping[str, VariableType],
        collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
        key_or_index: typing.Union[str, int],
        encountered_value: ExpressionVariableType
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
        encountered_value: ExpressionVariableType
    ) -> bool:
        if not isinstance(encountered_value, str):
            return False

        return ExpressionPattern.search(encountered_value) is not None

    def apply_expression(
        current_variables: typing.Mapping[str, VariableType],
        collection: typing.Union[typing.MutableMapping, typing.MutableSequence],
        key_or_index: typing.Union[str, int],
        encountered_value: ExpressionVariableType
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