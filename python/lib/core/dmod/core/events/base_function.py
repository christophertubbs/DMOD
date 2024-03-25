"""
Classes used to organize, validate, and orchestrate function calls
"""
from __future__ import annotations

import asyncio
import typing
import inspect
import logging

from collections.abc import Collection

from pydantic import BaseModel
from pydantic import Field

from pydantic import root_validator

from typing_extensions import ParamSpec
from typing_extensions import Concatenate

PARAMS = ParamSpec("PARAMS")
_T = typing.TypeVar("_T")


SpecialForms: typing.Tuple = (
    typing.Any,
    typing.NoReturn,
    typing.ClassVar,
    typing.Union,
    typing.Final,
    typing.Optional,
    typing.Literal
)
"""
A series of special typing indicators that denote that an object has some sort of special behavior
"""

SpecialWrappers: typing.Tuple = (
    typing.Union,
    typing.Optional,
    typing.Literal
)
"""
A series of special typing indicators that denote that the arguments within the type are more important than the origin
"""


def value_is_member_of_wrapper(possible_wrapper: typing.Type, value) -> bool:
    wrapper_base = typing.get_origin(possible_wrapper)

    if not wrapper_base in SpecialWrappers:
        return False

    value_is_type = isinstance(value, type)
    arguments = typing.get_args(possible_wrapper)

    if wrapper_base == typing.Union:
        for wrapper_argument in arguments:
            if value_is_member_of_wrapper(wrapper_argument, value):
                return True

            argument_base = typing.get_origin(wrapper_argument)

            if argument_base is None and value_is_type and issubclass(value, wrapper_argument):
                return True
            elif argument_base is None and isinstance(value, wrapper_argument):
                return True
            elif value_is_type and issubclass(value, argument_base):
                # Will return True if the base is
                return True

    elif wrapper_base == typing.Literal:
        has_positively_wrapped_member = any(
            value_is_member_of_wrapper(typing.get_origin(arg), value)
            for arg in arguments
            if typing.get_origin(arg) in SpecialWrappers
        )

        if has_positively_wrapped_member:
            return True

        return value in arguments

    return False


def is_special_form(obj) -> bool:
    """
    Indicates whether the passed object is some sort of special form

    Args:
        obj: The item to test

    Returns:
        True if python considers the object one of its special forms
    """
    root_type = typing.get_origin(obj) or obj
    return root_type in SpecialForms

def is_special_wrapper(obj) -> bool:
    """
    Indicates whether the passed object is a wrapping for another type

    Args:
        obj: The item to test

    Returns:
        True if the value from `typing.get_args` is more important than the origin value
    """
    root_type = typing.get_origin(obj) or type
    return root_type in SpecialWrappers


class Event(typing.Generic[_T]):
    """
    Base class for basic information sent to event handlers
    """
    def __init__(self, event_name: str, caller: _T, *args, **kwargs):
        self.__event_name: str = event_name
        self.__caller: _T = caller
        self.__positional_parameters: typing.Sequence[typing.Any, ...] = tuple(args)
        self.__keyword_parameters: typing.Dict[str, typing.Any] = dict(kwargs)

    @property
    def event_name(self) -> str:
        """
        The name of the event being triggered
        """
        return self.__event_name

    @property
    def kwargs(self) -> typing.Mapping[str, typing.Any]:
        """
        All parameters sent to handlers
        """
        return self.__keyword_parameters.copy()

    @property
    def args(self) -> typing.Sequence[typing.Any]:
        """
        All positional parameters sent to handlers
        """
        return tuple(self.__positional_parameters)

    @property
    def caller(self) -> _T:
        """
        The entity that triggered the event
        """
        return self.__caller


EventHandler = typing.Callable[
    Concatenate[
        Event,
        PARAMS
    ],
    typing.Union[typing.Coroutine, typing.Any]
]
"""
A function that accepts event metadata and any other parameters, returning any sort of result
"""


class BasicParameter(typing.TypedDict):
    """
    Represents basic parameter information if passed via dictionary
    """
    index: int
    name: str
    type: typing.Optional[typing.Union[type, str]]
    is_kwargs: typing.Optional[bool]
    is_args: typing.Optional[bool]
    default: typing.Optional[typing.Any]
    required: typing.Optional[bool]


class EventFunctionParameter(BaseModel):
    """
    Formal data about a specific parameter within the expectations of an event handler's signature
    """
    class Config:
        """
        Inner configuration class that allows the EventFunctionParameter to use generic types that pydantic
        can't serialize
        """
        arbitrary_types_allowed=True

    index: int = Field(description="The index of the parameter within the signature")
    """The index of the parameter within the signature"""

    name: str = Field(description="The name of the parameter in the signature")
    """The name of the parameter in the signature"""

    type: typing.Optional[typing.Union[type, str, Collection, typing.Any]] = Field(
        default=None,
        description="The expected type of value passed through the parameter"
    )
    """The expected type of value passed through the parameter"""

    is_kwargs: typing.Optional[bool] = Field(default=False)
    """Whether the parameter represents variable keyword arguments"""

    is_args: typing.Optional[bool] = Field(default=False)
    """Whether the parameter represents variable positional arguments"""

    default: typing.Optional[typing.Any] = Field(default=None)
    """A default value to if one was not supplied"""

    required: typing.Optional[bool] = Field(default=False)
    """Whether it is required for this parameter be provided when invoking the corresponding function"""

    positional_only: typing.Optional[bool] = Field(default=False)
    """Whether this parameter may only be passed via position"""

    keyword_only: typing.Optional[bool] = Field(default=False)
    """Whether this parameter may only be passed via keyword"""

    @property
    def acceptable_types(self) -> typing.Optional[typing.Set[type]]:
        """
        Get a set of all types that are accepted by this parameter

        Returns:
            A set of all types if they were passed. None it can be anything
        """
        if self.type in (None, typing.Any) or isinstance(self.type, str):
            return None

        types = set()
        types_to_check = []

        if isinstance(self.type, typing.Collection) and len(self.type) > 0:
            types_to_check.extend(
                self.type
            )
        elif not isinstance(self.type, typing.Collection):
            types_to_check.append(self.type)

        for type_to_check in types_to_check:
            root_type = typing.get_origin(type_to_check)
            if is_special_wrapper(type_to_check):
                wrapped_types = typing.get_args(type_to_check)
                for wrapped_type in wrapped_types:
                    if not isinstance(wrapped_type, type):
                        types.add(type(wrapped_type))
                        continue

                    root_type = typing.get_origin(wrapped_type)

                    if root_type is None:
                        types.add(wrapped_type)
                    elif root_type == typing.Literal:
                        types.union({
                            type(literal_value)
                            for literal_value in typing.get_args(wrapped_type)
                        })
                    else:
                        types.add(root_type)
            elif isinstance(type_to_check, typing._GenericAlias):
                types.add(getattr(typing, type_to_check._name))
            else:
                types.add(typing.get_origin(type_to_check) or type_to_check)

        return types

    def allows_value_type(self, value_type: typing.Type) -> bool:
        if self.is_args or self.is_kwargs or self.type is None:
            return True

        if isinstance(self.type, str):
            # Can't easily check if the type given is valid, so we're just going to say True for now.
            #   Stating False will return an incorrect value when the value DOES fit, which is more important than
            #   it returning false when it doesn't (thank you, duck typing)
            return True

        if isinstance(self.type, typing.Collection) and len(self.type) > 0:
            for collected_type in self.type:
                if is_special_wrapper(collected_type) and value_is_member_of_wrapper(collected_type, value_type):
                    return True

                if typing.get_origin(collected_type):
                    collected_type = typing.get_origin(collected_type)
                elif not isinstance(collected_type, type):
                    collected_type = type(collected_type)

                if isinstance(value_type, type):
                    return issubclass(value_type, collected_type)

                return isinstance(value_type, collected_type)
        elif is_special_wrapper(self.type):
            return value_is_member_of_wrapper(self.type, value_type)
        elif isinstance(self.type, type):
            if isinstance(value_type, type):
                return issubclass(value_type, self.type)
            return isinstance(value_type, self.type)

        return True

    def compatible_with(self, other: EventFunctionParameter) -> bool:
        """
        Determines whether THIS parameter can be used in place of the other

        For instance, if this parameter is for `SomeChildOfEvent` and the other parameter is for `Event`, this will return True.
        If this parameter is for `Event` and the other parameter is for `SomeChildOfEvent`, this will return False.

        This is not transitive - this may be compatible with other while other is not compatible with this.

        Examples:
            >>> first = EventFunctionParameter(index=0, name="first", type=str)
            >>> second = EventFunctionParameter(index=9, name="second", type=typing.Union[str, int, bool])
            >>> third = EventFunctionParameter(index=1, name="third", type=typing.Literal['cheese'])
            >>> args = EventFunctionParameter(index=0, name="args", is_args=True)
            >>> kwargs = EventFunctionParameter(index=1, name="kwargs", is_kwargs=True)
            >>> first.compatible_with(second)
            True
            # An invocation with the parameter named 'first' will satisfy the needs of the parameter named 'second'
            # since it should only ever be a string and `second` can handle strings, ints, and booleans
            >>> second.compatible_with(first)
            False
            # An invocation with the parameter 'second' will not satisfy the needs of the parameter named 'first'
            # since 'second' should handle strings, ints, and booleans and 'first' must be a str
            >>> first.compatible_with(third)
            False
            # 'first' should handle any string but 'third' should only handle the string of 'cheese'
            >>> third.compatible_with(first)
            True
            # 'third' must accept the string 'cheese' whereas 'first' accepts any string. A similar call with
            # 'third' will fit a call with 'first'

        Args:
            other: The other parameter to check

        Returns:
            True if this parameter can fulfill the needs of the other parameter
        """
        for parameter_type in self.acceptable_types:
            for other_type in other.acceptable_types:
                if isinstance(parameter_type, type):
                    type_matches = issubclass(parameter_type, other_type)
                else:
                    type_matches = isinstance(parameter_type, other_type)

                if type_matches:
                    return True
        return False

    @classmethod
    def from_basic_parameter(cls, parameter: BasicParameter) -> EventFunctionParameter:
        """
        Create a parameter based on a dictionary of metadata

        Args:
            parameter: A dictionary of basic metadata about a single parameter within a function signature

        Returns:
            A formal parameter representation
        """
        instantiation_parameters = {
            "index": parameter['index'],
            "name": parameter['name'],
            "is_kwargs": parameter.get("is_kwargs", False),
            "is_args": parameter.get("is_args", False),
            "required": parameter.get("required", False)
        }

        if "type" in parameter:
            instantiation_parameters["type"] = parameter['type']

        if "default" in parameter:
            instantiation_parameters["default"] = parameter['default']

        return cls(**instantiation_parameters)

    @classmethod
    def from_function(cls, function: EventHandler) -> typing.Sequence[EventFunctionParameter]:
        """
        Create a series of parameters from a function signature

        Args:
            function: The function to create the parameters from

        Returns:
            A series of parameter metadata for each parameter in the passed function
        """
        function_parameters = {
            name_and_parameter[0]: {
                "index": parameter_index,
                "name": name_and_parameter[0],
                "type": [],
                "default": name_and_parameter[1].default,
                "empty": name_and_parameter[1].empty,
                "kind": name_and_parameter[1].kind,
                "VAR_POSITIONAL": name_and_parameter[1].VAR_POSITIONAL,
                "VAR_KEYWORD": name_and_parameter[1].VAR_KEYWORD,
                "KEYWORD_ONLY": name_and_parameter[1].KEYWORD_ONLY,
                "POSITIONAL_ONLY": name_and_parameter[1].POSITIONAL_ONLY
            }
            for parameter_index, name_and_parameter in enumerate(inspect.signature(function).parameters.items())
        }

        for parameter_name, parameter_hint in typing.get_type_hints(function).items():
            # 'return' might end up in the type hints describing what is returned - scratch that if it shows up
            if parameter_name not in function_parameters:
                continue

            parameter_origin = typing.get_origin(parameter_hint)
            parameter_arguments = typing.get_args(parameter_hint)

            if parameter_origin and not is_special_form(parameter_origin):
                function_parameters[parameter_name]["type"] = [parameter_origin]
            elif parameter_arguments:
                function_parameters[parameter_name]["type"] = [
                    typing.get_origin(arg) if typing.get_origin(arg) else arg
                    for arg in parameter_arguments
                    if isinstance(None, arg)
                ]
                if type(None) in parameter_arguments and function_parameters[parameter_name]['required']:
                    function_parameters[parameter_name]["required"] = False
                    function_parameters[parameter_name]["default"] = None

            elif parameter_origin:
                function_parameters[parameter_name]["type"] = [parameter_origin]
            else:
                function_parameters[parameter_name]["type"] = parameter_hint

        parameters: typing.List[cls] = []

        for name, metadata in function_parameters.items():
            parameter_kind = metadata['kind']

            empty = metadata['empty']
            is_variable_positional_argument = parameter_kind is metadata['VAR_POSITIONAL']
            is_variable_keyword_argument = parameter_kind is metadata['VAR_KEYWORD']
            is_keyword_only_argument = parameter_kind is metadata['KEYWORD_ONLY']
            is_positional_only_argument = parameter_kind is metadata['POSITIONAL_ONLY']

            default = metadata['default']

            if is_variable_positional_argument or is_variable_keyword_argument:
                required = False
            else:
                required = default is empty

            parameter = cls(
                index=metadata['index'],
                name=name,
                type=metadata['type'],
                default=default,
                required=required,
                positional_only=is_positional_only_argument,
                keyword_only=is_keyword_only_argument,
                is_args=is_variable_positional_argument,
                is_kwargs=is_variable_keyword_argument
            )

            parameters.append(parameter)

        return parameters

    @property
    def can_use_positional_or_keyword(self) -> bool:
        """
        Whether the parameter may be passed as either a positional OR keyword argument
        """
        return not (self.positional_only or self.keyword_only)

    @property
    def is_required_and_positional_only(self) -> bool:
        """
        Whether the parameter must be passed and cannot be passed via keyword
        """
        return self.required and self.positional_only

    @root_validator
    def _correct_expectations(cls, values: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        """
        Correctly mark if passed values indicate if this parameter is required

        Args:
            values: The values to be deserialized so far

        Returns:

        """
        keyword_only = values.get("keyword_only", False)
        is_args = values.get("is_args", False)
        is_kwargs = values.get("is_kwargs", False)
        has_default = "default" in values

        if "required" not in values and (keyword_only or is_args or is_kwargs or has_default):
            values['required'] = False

        return values

    def is_valid(self, value) -> bool:
        """
        Determines if the passed value may be used for this parameter

        Args:
            value: The value to check

        Returns:
            True if the passed value may be used as this parameter
        """
        if self.type is None:
            return True

        origin = typing.get_origin(self.type) or self.type

        return isinstance(value, origin)

    def __hash__(self):
        return hash((self.required, self.name, self.type, self.positional_only, self.keyword_only))

    def __str__(self):
        if self.is_args:
            return f"*{self.name}"
        if self.is_kwargs:
            return f"**{self.name}"

        if self.type and isinstance(self.type, typing.Sequence) and len(self.type) > 1:
            type_description = f": ({', '.join(str(parameter_type) for parameter_type in self.type)})"
        elif self.type and isinstance(self.type, typing.Sequence):
            type_description = f": {self.type[0]}"
        elif self.type:
            type_description = f": {self.type}"
        else:
            type_description = ''

        if not self.required and self.default != inspect.Parameter.empty:
            default_description = f" = {self.default}"
        else:
            default_description = ""

        return f"{self.name}" \
               f"{type_description}" \
               f"{default_description}"

    def __repr__(self):
        return str(self)


def make_args(name: str = None, index: int = None) -> EventFunctionParameter:
    """
    Shortcut to create a variable positional argument

    Args:
        name: The name of the positional argument. Defaults to 'args'
        index: The index of the variable positional argument

    Returns:
        A parameter that represents the stardard args parameter
    """
    if name is None:
        name = "args"

    return EventFunctionParameter(
        name=name,
        index=index,
        is_args=True,
        is_kwargs=False,
        required=False
    )


def make_kwargs(name: str = None, index: int = None) -> EventFunctionParameter:
    """
    Shortcut to create a variable keyword argument

    Args:
        name: The name of the keyword argument. Defaults to: 'kwargs'
        index: The index of the variable keyword argument

    Returns:
        A parameter that represents the standard kwargs parameter
    """
    if name is None:
        name = "kwargs"

    return EventFunctionParameter(
        name=name,
        index=index,
        is_args=False,
        is_kwargs=True,
        required=False
    )


class Signature(typing.Sequence[EventFunctionParameter]):
    """
    Details the parameters used to call a function
    """
    def __getitem__(self, index) -> EventFunctionParameter:
        return self.__parameters[index]

    def __len__(self) -> int:
        return len(self.__parameters)

    @classmethod
    def from_function(cls, function: EventHandler) -> Signature:
        """
        Create a signature by getting the individual parameters from a function

        Args:
            function: The function to create a signature for

        Returns:
            The signature describing the parameters in the function
        """
        return cls(parameters=EventFunctionParameter.from_function(function))

    def __init__(self, parameters: typing.Iterable[typing.Union[dict, BasicParameter, EventFunctionParameter]]):
        """
        Args:
            parameters: The parameters that fit within this signature
        """
        self.__parameters = []

        for index, parameter in enumerate(parameters):
            if isinstance(parameter, EventFunctionParameter):
                self.__parameters.append(parameter)
            elif isinstance(parameter, dict):
                parameter.update({"index": index})
                self.__parameters.append(EventFunctionParameter.from_basic_parameter(parameter))
            else:
                types = ', '.join([type(param) for param in parameters])
                raise TypeError(
                    f"Cannot register an event with the proposed signature with arguments ({types}). "
                    f"Only dictionaries and EventFunctionParameters are allowed"
                )

    @property
    def parameters(self) -> typing.Sequence[EventFunctionParameter]:
        """
        The parameters within this signature
        """
        return self.__parameters

    @property
    def has_args(self):
        return bool([
            parameter
            for parameter in self.__parameters
            if parameter.is_args
        ])

    @property
    def has_kwargs(self) -> bool:
        return bool([
            parameter
            for parameter in self.__parameters
            if parameter.is_kwargs
        ])

    @property
    def keywords(self) -> typing.Set[str]:
        return {
            parameter.name
            for parameter in self.__parameters
            if not parameter.positional_only
        }

    @property
    def required_keywords(self) -> typing.Set[str]:
        return {
            parameter.name
            for parameter in self.__parameters
            if not parameter.positional_only
                and parameter.required
        }

    @property
    def is_universal(self) -> bool:
        universal = False
        if len(self.__parameters) == 2:
            universal = self.__parameters[0].is_args and self.__parameters[1].is_kwargs

        return universal

    @property
    def required_variable_count(self) -> int:
        count = 0

        for parameter in self.__parameters:
            if parameter.required:
                count += 1
            else:
                break

        return count

    def complies_with(self, expected_signature: Signature) -> bool:
        """
        Determines if this signature is valid if its matching arguments comply with the other signature

        Given:
            >>> def f(a, b, c, d=9, *args, val=4, **kwargs)

        The following are compatible:
            >>> def g(a, b, *args, **kwargs)
            >>> def h(*args, **kwargs)
            >>> def i(a, b, c, d=9, val=4, *args, **kwargs)

        The following are NOT compatible:
            >>> def j(a, b, c, d, *args, val=4, **kwargs)
            >>> def k(a, b, c, d=9, val=4, **kwargs)
            >>> def l()
            >>> def m(a)
            >>> def n(a, b, **kwargs)

        - j is not compatible because `d` is required. Other may be called without `d` anywhere, ex (1, 2, 3)
        - k is not compatible because it does not support *args, ex (1, 2, 3, 4, 5, 6, val1=5, val2="f")
        - l is not compatible because it doesn't support required parameters. a call like (1, 2, 3, 4, 5, 6, val1=5, val2="f") will fail
        - m is not compatible because it does not support all required parameters. A call like (1, 2, 3) will fail
        - n is not compatible because it does not support all required parameters and does not support *args. A call like (1, 2, 3) will fail.

        Given:
            >>> def f(a, b, *args)

        The following are compatible:
            >>> def g(a, b, c=9, *args)
            >>> def h(a, b, *args, **kwargs)
            >>> def i(a, b, *args, c=9)
            >>> def j(a, b, *args, c=9, **kwargs)
            >>> def k(*args, **kwargs)
            >>> def l(a, *args, **kwargs)

        The following are NOT compatible:
            >>> def m(a, b, c, *args, **kwargs)
            >>> def n(a, b, **kwargs)

        - m is not valid because it requires `c` which is not required to come through
        - n is not compatible because it does not have *args. A call like (1, 2, 3, 4, 5, 6) will fail

        The function:
            >>> def f(*args, **kwargs)

        Only allows functions like:
            >>> def g(*args, **kwargs)

        If `other` is the universal (only has *args and **kwargs), this MUST be (*args, **kwargs).
        If this is (*args, **kwargs), `other` may be anything.

        Parameter types are not considered due to duck typing.
        Mismatched types should only be checked when the function is called.

        Args:
            expected_signature: The signature that THIS signature must comply with

        Returns:
            Whether this signature can handle all the possible arguments passed to the other's function
        """
        # False if anything may come through the other signature but not this signature
        if expected_signature.is_universal and not self.is_universal:
            return False

        # True if this can handle any possible argument
        if self.is_universal:
            return True

        # TODO: No, this should not be a major problem -
        # False if this has less required variables and doesn't have args
        #if self.required_variable_count > expected_signature.required_variable_count and not expected_signature.has_args:
        #    return False

        # False if it is expected to allow *args but this doesn't
        if not self.has_args and expected_signature.has_args:
            return False

        # False if it is expected to allow **kwargs but this doesn't
        if not self.has_kwargs and expected_signature.has_kwargs:
            return False

        # False if this doesn't have all the required keywords and this doesn't kwargs
        if not self.keywords.issubset(expected_signature.required_keywords) and not self.has_kwargs:
            return False

        # Required variables may be subverted if *args or **kwargs are supported in both. If they aren't,
        # this signature only complies if it has the same number of required variables as the other
        if not (self.has_kwargs or expected_signature.has_kwargs or self.has_args or expected_signature.has_args):
            if self.required_variable_count != expected_signature.required_variable_count:
                return False

        return True

    def __hash__(self) -> int:
        return hash(tuple(self.__parameters))

    def __iter__(self):
        return iter(self.__parameters)

    def __str__(self):
        return f"({', '.join([str(parameter) for parameter in self])})"

    def __repr__(self):
        return str(self)


class EventFunction(EventHandler):
    """
    Represents a function to call when an event is triggered
    """
    def __init__(self, function: EventHandler, allow_errors: bool = None):
        self.__function = function
        parameters: Signature = Signature.from_function(function)

        first_parameter: typing.Optional[EventFunctionParameter] = parameters[0] if len(parameters) > 0 else None
        first_parameter_is_valid = False

        # The first parameter is valid if:
        #   - It has no type but its name has 'event' or 'evt' in it
        #   - It is *args,
        #   - It is a subclass of the Event class
        #   - It is a union that contains some subclass of Event

        if first_parameter is None:
            # The first parameter cannot be valid if there ISN'T a first parameter
            first_parameter_is_valid = False
        elif first_parameter.is_args:
            # If the first parameter is *args we know that an arbitrary amount of positional parameters are allowable,
            # meaning that sticking the event in has few if any side effects
            first_parameter_is_valid = True
        elif first_parameter.is_kwargs:
            first_parameter_is_valid = False
        elif parameters[0].type is None and "event" in parameters[0].name.lower() or 'evt' in parameters[0].name.lower():
            # If no annotation is given at all, we'll just assume an event type can be inserted due to duck typing
            first_parameter_is_valid = True
        elif "event" in parameters[0].type.lower() or 'evt' in parameters[0].type.lower():
            # We go ahead and assume a type description containing something like '.*event.*' might describe
            # something like 'MouseEvent' or 'ClickEvent' or 'BasicEvent', etc.
            # We go ahead and cross our fingers and accept it.
            first_parameter_is_valid = True

        if not first_parameter_is_valid:
            raise TypeError(
                f"'{function.__name__}' is not a valid event handler - "
                f"the first parameter MUST be an Event State-like object"
            )

        self.__parameters = parameters
        self.__allow_errors = bool(allow_errors)
        self.__has_positional_only = any(parameter.positional_only for parameter in parameters)
        self.__has_keyword_only = any(parameter.keyword_only for parameter in parameters)
        self.__has_kwargs = parameters.has_kwargs
        self.__has_args = parameters.has_args
        self.__args_index: typing.Optional[int] = None
        self.__kwargs_index: typing.Optional[int] = None

        for index, parameter in enumerate(parameters):
            if parameter.is_kwargs:
                self.__kwargs_index = index

            if parameter.is_args:
                self.__args_index = index

        self.__required_parameters: typing.List[EventFunctionParameter] = [
            parameter
            for parameter in parameters
            if parameter.required
        ]

        signature = inspect.signature(function)

        if signature.return_annotation is not signature.empty:
            self.__return_type: typing.Optional[str] = str(signature.return_annotation)
        else:
            self.__return_type: typing.Optional[str] = None

    @property
    def required_parameters(self) -> typing.Sequence[EventFunctionParameter]:
        return self.__required_parameters

    @property
    def is_async(self) -> bool:
        return inspect.iscoroutinefunction(self.__function)

    @property
    def parameters(self) -> Signature:
        return self.__parameters

    @property
    def parameter_hash(self) -> int:
        return hash(self.__parameters)

    def __call__(self, event: Event, *args, **kwargs) -> typing.Union[typing.Coroutine, typing.Any]:
        try:
            return self.__function(event, *args, **kwargs)
        except BaseException as exception:
            if self.__allow_errors:
                logging.error(str(exception), exc_info=exception)
            else:
                raise

    @property
    def parameter_descriptions(self) -> typing.Sequence[str]:
        descriptions = []

        if self.__has_positional_only:
            descriptions.extend([
                str(parameter)
                for parameter in self.__parameters
                if parameter.positional_only
            ])
            descriptions.append("/")

        descriptions.extend([
            str(parameter)
            for parameter in self.__parameters
            if parameter.can_use_positional_or_keyword
        ])

        if self.__has_keyword_only:
            descriptions.append("*")
            descriptions.extend([
                str(parameter)
                for parameter in self.__parameters
                if parameter.keyword_only
            ])

        return descriptions

    @property
    def kwargs_index(self) -> typing.Optional[int]:
        return self.__kwargs_index

    @property
    def args_index(self) -> typing.Optional[int]:
        return self.__args_index

    @property
    def has_args(self) -> bool:
        return self.__has_args

    @property
    def has_kwargs(self) -> bool:
        return self.__has_kwargs

    def __str__(self):
        return f"{self.__function.__name__}" \
               f"({', '.join(self.parameter_descriptions)})" \
               f"{' -> ' + self.__return_type if self.__return_type else ''}"

    def __repr__(self):
        return str(self)


class EventFunctionGroup:
    """
    A collection of event handlers with a unified signature
    """
    def __init__(
        self,
        expected_arguments: typing.Iterable[EventFunctionParameter],
        *functions: typing.Union[EventFunction, typing.Callable],
        allow_errors: bool = None
    ):
        self.__expected_arguments: Signature = Signature(expected_arguments)

        invalid_functions: typing.List[str] = []

        self.__functions: typing.List[EventFunction] = []

        for function in (functions or []):
            self.add_function(
                function,
                invalid_functions,
                allow_errors
            )

        if invalid_functions:
            parameter_signatures = ', '.join([str(parameter) for parameter in expected_arguments])
            raise ValueError(
                f"Attempted to create an invalid function group. The desired signature is ({parameter_signatures}), "
                f"but instead received the following non-conforming functions: {', '.join(invalid_functions)}"
            )

    @property
    def signature(self) -> Signature:
        return self.__expected_arguments

    def add_function(
        self,
        function: typing.Union[EventFunction, typing.Callable],
        invalid_functions: typing.List[str],
        allow_errors: bool = None
    ):
        if not isinstance(function, EventFunction):
            try:
                function = EventFunction(function, allow_errors)
            except:
                if not allow_errors:
                    raise
                invalid_functions.append(function.__qualname__)
                return

        if self.signature_matches(function):
            self.__functions.append(function)
        else:
            invalid_functions.append(str(function))

    def signature_matches(
        self,
        function: typing.Union[EventFunction, typing.Callable],
        allow_errors: bool = None
    ) -> bool:
        """
        Determines if the given function conforms to the requirements of this event group

        The passed function must be callable with what was declared

        Args:
            function: The function to check
            allow_errors: Log errors instead of raising the exception

        Returns:

        """
        if not isinstance(function, EventFunction):
            try:
                function = EventFunction(function, allow_errors)
            except:
                # The function could not hack it as an event function, so it OBVIOUSLY can't match the signature
                return False

        return function.parameters.complies_with(self.__expected_arguments)

    async def fire(self, event: Event, *args, **kwargs) -> None:
        """
        Call all functions for this event and await any asynchronous results

        Args:
            event: The event being triggered
            *args: Positional arguments to send to each function
            **kwargs: Keyword arguments to send to each function
        """
        scheduled_async_functions: asyncio.Future = asyncio.gather(*[
            function(event, *args, **kwargs)
            for function in self.__functions
            if function.is_async
        ])

        exceptions: typing.List[BaseException] = []

        synchronous_functions: typing.List[EventHandler] = [
            func
            for func in self.__functions
            if not func.is_async
        ]

        for function in synchronous_functions:
            function(event, *args, **kwargs)

        results = list(await scheduled_async_functions)

        # Loop through all results in a while loop rather than a for-loop
        #   awaited results will be placed back into the collection for iteration
        while results:
            result = results.pop()
            if isinstance(result, BaseException):
                exceptions.append(result)
            elif inspect.isawaitable(result):
                results.append(await result)

        if exceptions:
            raise Exception(exceptions)

    def trigger(self, event: Event, *args, **kwargs) -> typing.List[typing.Awaitable]:
        """
        Call all functions for this event synchronously

        Does not resolve asynchonous function calls. Must be done manually for the returned awaitables

        Args:
            event: The event being triggered
            *args: The positional arguments to send to each function
            **kwargs: Keyword arguments to send to each function

        Returns:
            A list of all awaitable artifacts created as a result of the function calls
        """
        coroutines: typing.List[typing.Awaitable] = []

        for function in self.__functions:
            result = function(event, *args, **kwargs)

            if inspect.isawaitable(result):
                coroutines.append(result)

        if len(coroutines) > 0:
            message = (f"{len(coroutines)} objects were left to be resolved by the handling of the "
                       f"'{event.event_name}' event")
            logging.debug(message)

        return coroutines

    def __call__(self, event: Event, *args, **kwargs) -> typing.List[typing.Awaitable]:
        """
        Call all functions for this event.

        Does not resolve asynchonous function calls. Must be done manually for the returned awaitables

        Args:
            event: The event being triggered
            *args: The positional arguments to send to each function
            **kwargs: Keyword arguments to send to each function

        Returns:
            A list of all awaitable artifacts created as a result of the function calls
        """
        return self.trigger(event, *args, **kwargs)
