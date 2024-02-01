"""
@TODO: Put a module wide description here
"""
from __future__ import annotations

import functools
import json
import abc
import types
import typing
import importlib
import inspect
import uuid

import pydantic

from .common import exists


class CannotSerializeError(Exception):
    """
    An error that arises when something cannot be serialized
    """
    ...


class InvalidRestorableError(Exception):
    """
    An error that arises when something cannot be considered as a Restorable object
    """
    ...


_SENTINEL_VALUE = uuid.uuid1()
"""A value representing non-existence in situations where None, null, or NaN are valid values"""


def describe_function(function: typing.Callable) -> str:
    return f"{function.__qualname__}{inspect.signature(function)}"


def get_element(module_name: str, element_name: str) -> typing.Any:
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise InvalidRestorableError(
            f"Cannot restore the item '{module_name}.{element_name}' - there is not module named '{module_name}'"
        ) from error

    element = module
    processed_name_parts = [
        module_name
    ]

    for name_part in element_name.split("."):
        processed_name_parts.append(name_part)

        element = getattr(element, name_part, _SENTINEL_VALUE)

        if element == _SENTINEL_VALUE:
            raise InvalidRestorableError(
                f"Cannot restore the item '{module_name}.{element_name}' "
                f"- nothing named '{'.'.join(processed_name_parts)}' can be found"
            )

    return element



def is_restorable_instance(data: typing.Union[bytes, str, typing.Mapping[str, typing.Any]]) -> bool:
    """
    Tests whether an object is something that may be considered as something that may be restored as a Restorable object

    Args:
        data: The data that might be valid for object restoration

    Returns:
        True if the data is worth trying to restore
    """
    if isinstance(data, bytes):
        data = data.decode()

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except:
            return False

    if not isinstance(data, typing.Mapping):
        return False

    if 2 > len(data) or len(data) > 4:
        return False

    if not isinstance(data.get("module"), str) or len(data.get("module")) < 2:
        return False

    if not isinstance(data.get("name"), str) or len(data.get("name")) < 3:
        return False

    if not isinstance(data.get("args"), (type(None), typing.Iterable)):
        return False

    if not isinstance(data.get("kwargs"), (type(None), typing.Mapping)):
        return False

    return True



class Package(pydantic.BaseModel):
    @classmethod
    def create(
        cls,
        module: str,
        name: str,
        arguments: typing.List[typing.Any] = None,
        keyword_arguments: typing.Dict[str, typing.Any] = None,
        **kwargs
    ):
        element = get_element(module_name=module, element_name=name)

        while cls in getattr(element, "__mro__", []):
            if not keyword_arguments:
                raise InvalidRestorableError(
                    f"Cannot restore a '{element.__class__.__qualname__}' - "
                    f"it lacks keyword arguments required to restore inner items"
                )

            if "module" not in keyword_arguments and "name" not in keyword_arguments:
                raise InvalidRestorableError(
                    f"Cannot restore the inner element of a {element.__class__.__qualname__} - "
                    f"the keyword arguments are missing both a module and a name"
                )
            elif "module" not in keyword_arguments:
                raise InvalidRestorableError(
                    f"Cannot restore the inner element of a {element.__class__.__qualname__} - "
                    f"the keyword arguments are missing a module name"
                )
            elif "name" not in keyword_arguments:
                raise InvalidRestorableError(
                    f"Cannot restore the inner element of a {element.__class__.__qualname__} - "
                    f"the keyword arguments are missing a name"
                )

            module = keyword_arguments['module']
            name = keyword_arguments['name']
            arguments = keyword_arguments.get("arguments")
            keyword_arguments = keyword_arguments.get("keyword_arguments")

            element = get_element(module_name=module, element_name=name)

        return cls(module=module, name=name, arguments=arguments, keyword_arguments=keyword_arguments, **kwargs)

    def __init__(
        self,
        *,
        module: str,
        name: str,
        arguments: typing.List[typing.Any] = None,
        keyword_arguments: typing.Dict[str, typing.Any] = None,
        **kwargs
    ):
        super().__init__(
            module=module,
            name=name,
            arguments=arguments or [],
            keyword_arguments=keyword_arguments or {},
            **kwargs
        )

    module: str = pydantic.Field(description="The name of the module that contains the item to restore", min_length=1)
    """The name of the module that contains the item to restore"""

    name: str = pydantic.Field(description="The name of the object to restore", min_length=1)
    """The name of the object to restore"""

    arguments: typing.Optional[
        typing.List
    ] = pydantic.Field(
        default_factory=list,
        description="Positional Arguments used to restore the object"
    )
    """Positional Arguments used to restore the object"""

    keyword_arguments: typing.Optional[
        typing.Dict[str, typing.Any]
    ] = pydantic.Field(
        default_factory=dict,
        description="Keyword arguments used to restore the object"
    )
    """Keyword arguments used to restore the object"""

    is_function: typing.Optional[bool] = pydantic.Field(
        default=False,
        description="Whether this should be restored as a function rather than a value"
    )
    """Whether this should be restored as a function rather than a value"""


class RestoredPackage(Package):
    @classmethod
    def _interpret_value(
        cls,
        value: typing.Union[RestoredPackage, typing.List[RestoredPackage], typing.Dict, typing.Any]
    ) -> typing.Any:
        if value is None or isinstance(value, (str, int, float, bytes, Restorable)):
            return value

        if isinstance(value, typing.Mapping):
            try:
                value = RestoredPackage(**value)
            except:
                pass

        if isinstance(value, RestoredPackage):
            value = value.restore()
        elif isinstance(value, typing.Mapping):
            value = {
                key: cls._interpret_value(inner_value)
                for key, inner_value in value.items()
            }
        elif isinstance(value, typing.Iterable):
            value = [
                cls._interpret_value(arg)
                for arg in value
            ]

        return value

    @pydantic.validator("arguments")
    def convert_positional_arguments(cls, values: typing.List[typing.Any]) -> typing.List[typing.Any]:
        return [
            cls._interpret_value(value)
            for value in (values or [])
        ]

    @pydantic.validator("keyword_arguments")
    def convert_keyword_arguments(cls, values: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        return {
            key: cls._interpret_value(value)
            for key, value in (values or {}).items()
        }

    @pydantic.validator("module")
    def validate_module(cls, module_name: str) -> str:
        if module_name == "__main__":
            raise InvalidRestorableError(
                f"Items from '__main__' cannot be restored since the state of '__main__' might be different "
                f"in different contexts"
            )

        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            raise ModuleNotFoundError(
                f"Cannot use '{module_name}' as a module for a function - it can't be found"
            ) from error

        return module_name

    @pydantic.root_validator
    def validate_field(cls, values: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        field = get_element(values['module'], values['name'])

        # The object that will be called MUST be callable, but it can't be async - the caller itself may not be async
        # TODO: Remove this stipulation if asyncio.async_to_sync is to be used
        if isinstance(field, typing.Callable) and inspect.iscoroutinefunction(field):
            raise TypeError(
                f"'{values['module']}.{values['name']}' cannot be used as a restorable "
                f"function it must be callable and cannot be asynchronous"
            )

        return values

    def get_module(self) -> types.ModuleType:
        return importlib.import_module(self.module)

    @property
    def value(self) -> typing.Any:
        return get_element(self.module, self.name)

    def restore(self, *args, **kwargs):
        value = self.value

        args = [arg for arg in args] + self.arguments
        kwargs.update(self.keyword_arguments)

        if callable(value) and self.is_function:
            return functools.partial(value, *args, **kwargs)

        if callable(value):
            value = value(*args, **kwargs)

        while callable(value):
            value = value()

        return value

    def __call__(self, *args, **kwargs):
        return self.restore(*args, **kwargs)


class PackagedRestorable(Package):
    @pydantic.root_validator
    def validate_package(cls, package: typing.Dict[str, typing.Any]):
        try:
            #json.dumps(package)
            pass
        except:
            raise InvalidRestorableError(f"Cannot package {cls} - the generated data cannot be serialized")
        return package

    @classmethod
    def from_function(cls, function: typing.Callable, *args, **kwargs) -> PackagedRestorable:
        if not callable(function):
            raise CannotSerializeError(
                f"A {cls.__qualname__} cannot be created from '{function}' - "
                f"{cls.__qualname__}.from_function expects a callable object and {function} is not one"
            )

        if function.__name__ == "<lambda>":
            raise CannotSerializeError(
                f"A {cls.__qualname__} cannot be created from an anonymous function"
            )

        function_name = function.__qualname__
        module_name = inspect.getmodule(function).__name__

        return PackagedRestorable(
            module=module_name,
            name=function_name,
            args=args,
            kwargs=kwargs,
            is_function=True
        )

    def restore(self, *args, **kwargs) -> typing.Any:
        """
        Restore the item described within the package

        Args:
            *args: Positional args to use when unpacking the object
            **kwargs: Keyword arguments to use when unpacking the object

        Returns:
            The restored item
        """
        restored_package = RestoredPackage(**self.dict())
        return restored_package.restore(*args, **kwargs)


class Restorable(abc.ABC):
    """
    An object that may be restored based upon a packaging map
    """
    def create_restorable_package(self, *args, **kwargs) -> PackagedRestorable:
        """
        Package up information needed to recreate this instance

        Returns:
            A mapping containing the package this object comes from, the constructor for said object,
            and the arguments to pass into the constructor
        """
        args = [*args, *self.get_package_arguments()]
        kwargs.update(self.get_package_keyword_arguments())

        package = PackagedRestorable(
            module=self.get_module_name(),
            name=self.get_restoring_name(),
            arguments=args,
            keyword_arguments=kwargs
        )

        return package

    def create_restorable_json(self) -> str:
        """
        Convert the restorable object into something that may be transmitted
        """
        package = self.create_restorable_package()
        return package.json(indent=4)

    def get_module_name(self) -> str:
        """
        Returns:
            The name of the module that contains the object used to restore this object
        """
        return inspect.getmodule(self.__class__).__name__

    def get_restoring_name(self) -> str:
        """
        Returns:
            The name of the function or object used to restore this object
        """
        return self.__class__.__name__

    @abc.abstractmethod
    def get_package_arguments(self) -> typing.List:
        """
        Get positional arguments for the field
        """
        ...

    @abc.abstractmethod
    def get_package_keyword_arguments(self) -> typing.Dict[str, typing.Any]:
        """
        Get keyword arguments for the field
        """
        ...


def get_class_definition_of_function(function: typing.Callable) -> typing.Optional[typing.Callable]:
    if function.__name__ == "<lambda>":
        return None

    if hasattr(function, "__self__"):
        owner = function.__self__

        if owner.__class__ != type:
            owner = owner.__class__

        function = getattr(owner, function.__name__, None)

    return function


def is_restorable_function(
    function: typing.Callable,
    caller_arg_count: int = None,
    kwargs: typing.Mapping = None
) -> bool:
    """
    Checks to see if a function can be serialized into a Restorable object

    Args:
        function: The function we seek to serialize
        caller_arg_count: The amount of positional parameters the caller intends to call the function with
        kwargs: Static keyword arguments that will be given when calling the function

    Returns:
        True if this function may be serialized within a restorable field
    """
    if kwargs is None:
        kwargs = {}

    if caller_arg_count is None:
        caller_arg_count = 0

    # This isn't a function that can be called if it isn't callable
    if not isinstance(function, typing.Callable):
        return False

    # TODO: Remove stipulation if asyncio.async_to_sync becomes involved
    if inspect.iscoroutinefunction(function):
        return False

    # If a function's name is '<lambda>', it means that the function isn't named and doesn't live in
    # the codebase in a way it may be rereferenced, as a result, it cannot be serialized and reconstructed
    if function.__name__ == "<lambda>":
        return False

    # If the class of the owner isn't a type, it means that we're working with an instance function,
    # which isn't valid here
    if hasattr(function, "__self__") and getattr(function, "__self__").__class__ != type:
        return False

    # Get the function at it's highest level. Most times this won't change the function, but if
    # `instance_of_x.class_method` is given, this will result in `X.class_method` since we won't have the instance
    # when deserializing
    non_member_function = get_class_definition_of_function(function)

    # If something happened and nothing came out on the other end, this can't be serialized
    if non_member_function is None:
        return False

    # Get the signature which will reveal details about the parameters
    function_signature = inspect.signature(non_member_function)

    parameters = [
        parameter
        for parameter in function_signature.parameters.values()
    ]
    """Parameters that may hold values when calling this function"""

    parameter_names = [
        parameter.name
        for parameter in parameters
        if parameter.kind not in (parameter.VAR_KEYWORD, parameter.VAR_POSITIONAL)
    ]
    """The names of each parameter"""

    missing_parameters = [
        keyword
        for keyword in kwargs
        if keyword not in parameter_names
    ]
    """Parameters that will be passed in that aren't in the signature"""

    has_args = exists(parameters, lambda parameter: parameter.kind == parameter.VAR_POSITIONAL)
    """Whether `*args` is in the signature"""

    has_kwargs = exists(parameters, lambda parameter: parameter.kind == parameter.VAR_KEYWORD)
    """Whether `**kwargs` is in the signature"""

    # This can't be serialized if the function can't receive the parameters that will be sent its way
    if missing_parameters and not has_kwargs:
        return False

    # Remove parameters that will be handled via `**kwargs` since they won't be called positionally
    parameters = [
        parameter
        for parameter in parameters
        if parameter.name in kwargs
        if parameter.kind != parameter.KEYWORD_ONLY
    ]

    required_positional_parameter_count = len([
        parameter
        for parameter in parameters
        if parameter.default == parameter.empty
    ])
    """The number of parameters that the caller MUST provide given that some might be handled via **kwargs"""

    # This isn't valid if the caller isn't going to provide enough arguments
    if required_positional_parameter_count > caller_arg_count:
        return False

    # This isn't valid if the function can't handle a variable additional arguments but
    # more arguments will be passed than are defined
    if not has_args and caller_arg_count > len(parameters):
        return False

    return True


class RestorableField(Restorable):
    """
    Defines a value that may come from a constant or function
    """
    @classmethod
    def from_function(
        cls,
        function: typing.Callable[[typing.Any], typing.Any],
        caller_argument_count: int = None,
        kwargs: typing.Mapping = None
    ) -> RestorableField:
        """
        Create a field based upon a passed in function

        Args:
            function: The function that will be used
            caller_argument_count: The number of positional arguments the caller expects to use
            kwargs: keyword arguments that will be passed to the function

        Returns:
            A RestorableField that essentially serializes the function
        """
        if not is_restorable_function(function, caller_arg_count=caller_argument_count, kwargs=kwargs):
            raise CannotSerializeError(f"Cannot create a restorable object based on '{describe_function(function)}'")

        usable_function = get_class_definition_of_function(function)

        # For the function `dmod.whatever.this.other.package.MyClass.do_something`, getting the module will give you the
        class_module = inspect.getmodule(usable_function).__name__
        function_name = usable_function.__name__

        return cls(field_module=class_module, field_name=function_name, kwargs=kwargs)

    def get_package_arguments(self) -> typing.List:
        return []

    def get_package_keyword_arguments(self) -> typing.Dict[str, typing.Any]:
        keyword_arguments = {
            "field_module": self.__field_module,
            "field_name": self.__field_name,
            "args": [arg for arg in self.__args or []],
            "kwargs": {
                key: value
                for key, value in (self.__kwargs or {}).items()
            }
        }

        try:
            json.dumps(keyword_arguments)
        except TypeError as type_error:
            raise CannotSerializeError(f"Cannot serialize kwargs for {self.name}: {keyword_arguments}") from type_error

        return keyword_arguments

    @property
    def name(self) -> str:
        """
        A simple name representation for the field
        """
        return f"{self.__field_module}.{self.__field_name}"

    def __init__(
        self,
        field_module: str = None,
        field_name: str = None,
        args: typing.Iterable = None,
        kwargs: typing.Mapping = None
    ):
        """
        Constructor

        Args:
            field_module: The name of the module containing the function
            field_name: The name of the function to call
            args: An optional collection of positional arguments for the function
            kwargs: An optional mapping of keyword arguments for the function
        """
        # Make sure that given information may be serialized
        self.validate_and_get_field(field_module=field_module, field_name=field_name)
        self.validate_arguments(arguments=args, keyword_arguments=kwargs)

        self.__field_module = field_module
        """The name of the module that contains the field"""

        self.__field_name = field_name
        """The name of the field to find"""

        self.__args = args or []
        """Positional arguments to use when calling the field if it is a function"""

        self.__kwargs = kwargs or {}
        """Keyword arguments to use when calling the field if it is a function"""

    def validate_and_get_module(self, module_name: str = None):
        """
        Ensure that the module exists

        Args:
            module_name: The name of the module to search for
        """
        if not module_name and self.__field_module:
            module_name = self.__field_module
        elif not module_name:
            raise InvalidRestorableError(
                f"The module name for a {self.__class__.__name__} is not valid - one was not given"
            )

        if module_name == "__main__":
            raise InvalidRestorableError(
                f"The {module_name} module cannot be used in a {self.__class__.__name__} since it might not be "
                f"available by the receiver of the packaged {self.__class__.__name__}"
            )

        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            raise ModuleNotFoundError(
                f"Cannot use '{module_name}' as a module for a function - it can't be found"
            ) from error

    def validate_and_get_field(
        self,
        field_module: str = None,
        field_name: str = None
    ) -> typing.Any:
        """
        Ensure that the indicated field is valid

        Args:
            field_module: The module for the function to validate
            field_name: The name of the function to validate
        """
        # If a name for the function wasn't passed but one is stored, use that one
        if not isinstance(field_name, str) and isinstance(self.__field_name, str):
            field_name = self.__field_name

        # If the module for the function wasn't passed but one is stored, use that one
        if not isinstance(field_module, str) and isinstance(self.__field_module, str):
            field_module = self.__field_module

        missing_specification = not isinstance(field_name, str) and not isinstance(field_module, str)

        # Fail the validation if neither a function nor module/function name is available
        if missing_specification:
            raise InvalidRestorableError(
                f"A restorable field cannot be validated - field name and module were not provided"
            )

        module = self.validate_and_get_module(module_name=field_module)

        # Iterate through each part of the name (delimited by '.') to find the desired object
        # This will help find objects like `MyClass.class_function`
        field_name_parts = field_name.split(".")

        field = None
        for field_name_part in field_name_parts:
            if field is None:
                field = getattr(module, field_name_part, _SENTINEL_VALUE)
            else:
                field = getattr(field, field_name_part, _SENTINEL_VALUE)
            if field == _SENTINEL_VALUE:
                break

        if field == _SENTINEL_VALUE:
            raise InvalidRestorableError(
                f"A {self.__class__.__name__} could not be created - "
                f"no value named '{field_name}' could be found in '{field_module}'"
            )

        # The object that will be called MUST be callable, but it can't be async - the caller itself may not be async
        # TODO: Remove this stipulation if asyncio.async_to_sync is to be used
        if isinstance(field, typing.Callable) and inspect.iscoroutinefunction(field):
            raise TypeError(
                f"'{field_module}.{field_name}' cannot be used as a restorable "
                f"function it must be callable and cannot be asynchronous"
            )

        return field

    def validate_arguments(self, arguments, keyword_arguments):
        """
        Ensure that passed arguments may be serialized for storage and transmission

        Args:
            arguments: Optional positional arguments for the function
            keyword_arguments: Optional keyword arguments for the function
        """
        if arguments is not None:
            try:
                json.dumps(arguments)
            except:
                raise InvalidRestorableError(
                    f"Invalid arguments for a {self.__class__.__name__} - the arguments for it cannot be serialized"
                )

        if keyword_arguments:
            try:
                json.dumps(keyword_arguments)
            except:
                raise InvalidRestorableError(
                    f"Invalid keyword arguments for a {self.__class__.__name__} - the arguments cannot be serialized"
                )

    def __str__(self):
        """
        The string representation.

        Should look something like: "some.module.in.project.Function(position1, position2, kwarg1=9, kwarg2='example')"
        """
        if not (self.__field_name and self.__field_module):
            return self.__class__.__name__

        representation = f"{self.__field_module}.{self.__field_name}"

        field = self.validate_and_get_field()

        if isinstance(field, typing.Callable):
            representation += "("
            clean_args = self.get_clean_args()

            if clean_args:
                representation += ", ".join(clean_args)

            clean_kwargs = self.get_clean_kwargs()

            if clean_kwargs:
                if clean_args:
                    representation += ", "

                representation += ", ".join([
                    f"{key}={value}"
                    for key, value in clean_kwargs.items()
                ])

            representation += ")"

        return representation

    def __repr__(self):
        return self.__str__()

    def get_clean_args(self) -> typing.List:
        """
        Unpack and prepare positional arguments for invocation

        Examples:
            >>> args = [
                9,
                "nine",
                {
                    "module": "dmod.core.common",
                    "name": "RestorableField",
                    "kwargs": {
                        "module_name": "redis",
                        "field_name": "get_connection"
                    }
                }
            ]
            >>> example = RestorableField(args=args)
            >>> example.get_clean_args()
            [9, "nine", <class Connection>]

        Returns:
            Positional arguments that are ready to be passed into the function
        """
        converted_args = []

        for arg in self.__args or []:
            previous_values = []

            while is_restorable_instance(arg):
                if arg in previous_values:
                    break

                previous_values.append(arg)

                arg = restore_value(arg)

                while isinstance(arg, RestorableField) and arg not in previous_values:
                    arg = arg()

            converted_args.append(arg)

        return converted_args

    def get_clean_kwargs(self) -> typing.Dict[str, typing.Any]:
        """
        Unpack and prepare keyword arguments for invocation

        Examples:
            >>> kwargs = {
                "kwarg1": 9,
                "kwarg2": "nine",
                "kwarg3": {
                    "module": "dmod.core.common",
                    "name": "RestorableField",
                    "kwargs": {
                        "module_name": "redis",
                        "field_name": "get_connection"
                    }
                }
            }
            >>> example = RestorableField(kwargs=kwargs)
            >>> example.get_clean_kwargs()
            {"kwarg1": 9, "kwarg2": "nine", "kwarg3": <class Connection>}

        Returns:
            keyword arguments that are ready to be passed into the function
        """
        converted_kwargs = {}

        for key, value in (self.__kwargs or {}).items():
            previous_values = []

            while is_restorable_instance(value):
                if value in previous_values:
                    break

                previous_values.append(value)

                value = restore_value(value)

                while isinstance(value, RestorableField) and value not in previous_values:
                    value = value()

            converted_kwargs[key] = value
        return converted_kwargs

    def __call__(self) -> typing.Any:
        """
        Returns:
            The value of the field
        """
        field = self.validate_and_get_field()

        if isinstance(field, typing.Callable):
            converted_args = self.get_clean_args()
            converted_kwargs = self.get_clean_kwargs()

            if converted_args and converted_kwargs:
                return field(*converted_args, **converted_kwargs)
            elif converted_args:
                return field(*converted_args)
            elif converted_kwargs:
                return field(**converted_kwargs)

            return field()

        return field

    def __eq__(self, other: RestorableField):
        if other is None:
            return False

        if not isinstance(other, self.__class__):
            return False

        return self() == other()


class RestorableFunction(RestorableField):
    def __call__(self, *args, **kwargs):
        function = self.validate_and_get_field()

        if not isinstance(function, typing.Callable):
            return function

        converted_args = self.get_clean_args()
        converted_kwargs = self.get_clean_kwargs()

        converted_kwargs.update(kwargs)
        converted_args.extend(args)

        prepared_function = functools.partial(function, *args, **kwargs)
        return prepared_function


def restore_value(data: typing.Mapping[str, typing.Any]) -> typing.Any:
    """
    Convert a `Restorable` mapping back into its instance

    Args:
        data: The mapping containing the data used to define a Restorable object

    Returns:
        The restored object
    """
    # Check to make sure the data even describes something that may be restored
    if not is_restorable_instance(data):
        raise TypeError(f"Cannot restore instance - the object described isn't restorable")

    # Create a function that may instantiate the object from the given parameters
    restoring_function = RestorableField(
        field_module=data["module"],
        field_name=data["name"],
        args=data.get('args'),
        kwargs=data.get('kwargs')
    )

    # Return the created object
    return restoring_function()


def restore_function(data: typing.Mapping[str, typing.Any], *args, **kwargs) -> typing.Callable:
    if not is_restorable_instance(data):
        raise TypeError(f"Cannot restore instance - the object described isn't restorable")

    restoring_function = RestorableFunction(
        field_module=data['module'],
        field_name=data['name'],
        args=data.get("args"),
        kwargs=data.get("kwargs")
    )

    return restoring_function(*args, **kwargs)