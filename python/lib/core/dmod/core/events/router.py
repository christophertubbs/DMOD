"""
Mechanism for routing event data to handlers
"""
from __future__ import annotations

import os
import typing
import inspect
import logging

from .base_function import EventFunctionParameter
from .base_function import Signature
from .base_function import EventFunctionGroup
from .base_function import Event
from .base_function import BasicParameter

SIGNATURE = typing.Union[
    Signature,
    typing.Callable,
    typing.Sequence[typing.Union[BasicParameter, EventFunctionParameter, dict]]
]
"""
Details that might shed light on what type of function signature should be used for a handler
"""

_T = typing.TypeVar("_T")

InvocationParameters = typing.Tuple[
    EventFunctionGroup,
    Event[_T],
    typing.Tuple[typing.Any, ...],
    typing.Mapping[str, typing.Any]
]


def validate_handler(handler: typing.Callable):
    """
    Throws an error if the passed handler cannot be used to react to an event

    Args:
        handler: The event handler to check
    """
    if isinstance(handler, type):
        raise TypeError(
            f"{handler.__qualname__} cannot be used as an event handler - "
            f"it is a type to be created, not a function to invoke logic"
        )

    if not isinstance(handler, typing.Callable):
        raise TypeError("Event handlers must be callable")


class EventRouter(typing.Generic[_T]):
    """
    Routes events and their payloads to their handlers
    """
    def __init__(
        self,
        fail_on_missing_event: bool = None,
        allow_errors: bool = None,
        events: typing.Dict[str, SIGNATURE] = None,
        **handlers: typing.Union[typing.Callable, typing.Sequence[typing.Callable]]
    ):
        """
        Constructor

        Args:
            fail_on_missing_event: Whether a routing call should throw an error if no matching event was registered. Default: False
            allow_errors: Allow errors to be logged rather than halt operations. Default: True
            events: A predefined mapping linking an event and what the event's handler signature should look like
            handlers: Handlers for events that should be registered
        """
        if events is None:
            events = {}

        self.__fail_on_missing_event: bool = fail_on_missing_event or False
        self.__allow_errors = allow_errors or True
        self.__events: typing.Dict[str, EventFunctionGroup] = {}
        self.__active_awaitables: typing.List[typing.Awaitable] = []

        for event_name, signature in events.items():
            self.register_event(event_name, signature)

        for event_name, event_handlers in handlers.items():
            self.register_handler(event_name, event_handlers)

    def register_event(self, event: str, signature: SIGNATURE) -> EventRouter:
        """
        Register a handler signature with an event

        Args:
            event: The name of the event to register
            signature: The expected signature for functions that will handle the event

        Returns:
            The updated EventRouter
        """
        if event in self.__events:
            return self

        if isinstance(signature, typing.Callable):
            signature: Signature = Signature.from_function(signature)
        elif isinstance(signature, typing.Sequence):
            signature = Signature(signature)

        self.__events[event] = EventFunctionGroup(signature, allow_errors=self.__allow_errors)
        return self

    def register_handler(
        self,
        event: str,
        handler: typing.Union[typing.Callable, typing.Sequence[typing.Callable]]
    ) -> EventRouter:
        """
        Attach a handler to an event

        Args:
            event: The name of the event that will have the handler attached to
            handler: A function to call when the event is triggered

        Returns:
            The updated router
        """
        if not handler:
            return self

        if not isinstance(handler, typing.Sequence):
            handler = list(handler) if isinstance(handler, typing.Iterable) else [handler]

        if not handler:
            return self

        for handler_function in handler:
            validate_handler(handler_function)

        if event not in self.__events:
            logging.debug(
                f"There is no registered event for '{event}' - "
                f"a new event is being registered but the required signatures may be incorrect."
            )
            self.register_event(event, handler[0])

        invalid_functions = []

        for event_handler in handler:
            self.__events[event].add_function(event_handler, invalid_functions, allow_errors=self.__allow_errors)

        if len(invalid_functions) > 0:
            separator = f"{os.linesep}    "
            message = (f"The following handlers cannot be added for the '{event}' event:"
                       f"{os.linesep}    {separator.join(invalid_functions)}"
                       f"{os.linesep}Expected:"
                       f"{os.linesep}    handler{self.__events[event].signature}")
            raise ValueError(message)

        return self

    async def complete_active_tasks(self):
        """
        Wait for all active tasks to be completed
        """
        while self.__active_awaitables:
            awaitable = self.__active_awaitables.pop()
            awaited_value = await awaitable

            if inspect.iscoroutine(awaited_value):
                self.__active_awaitables.append(awaited_value)

    def __prepare_call(
        self,
        event_name: str,
        caller: _T,
        *args,
        **kwargs
    ) -> InvocationParameters:
        """
        Get the proper elements needed to call event handlers

        Args:
            event_name: The name of the event to be triggered
            caller: Who is triggering the event
            *args: Positional arguments to be used when invoking functions
            **kwargs: keyword parameters to be used when invoking functions

        Returns:
            The group of functions to invoke, the event to provide, and all positional and keyword arguments
        """
        if event_name not in self.__events:
            raise KeyError(f"Cannot prepare for the '{event_name}' event if it was not previously registered")

        handler_group: EventFunctionGroup = self.__events[event_name]

        event_args: typing.List[typing.Any] = list(args)
        event_kwargs: typing.Dict[str, typing.Any] = dict(kwargs)

        # Loop through the positional arguments to see if there are any that should be moved to the event's
        # kwargs instead of the event's args
        if event_args:
            current_index = 0
            found_arg_indices: typing.List[int] = []

            for parameter in handler_group.signature:  # type: EventFunctionParameter
                if current_index >= len(event_args):
                    break

                if parameter.name in event_kwargs:
                    continue

                found_arg_indices.append(current_index)
                event_kwargs[parameter.name] = event_args[current_index]
                current_index += 1

            event_args = [
                arg
                for index, arg in enumerate(event_args)
                if index not in found_arg_indices
            ]

        event: Event[_T] = Event(event_name=event_name, caller=caller, *event_args, **event_kwargs)

        return handler_group, event, args, kwargs

    def trigger(self, event_name: str, caller: _T, *args, **kwargs):
        """
        Call all handlers for a given event synchronously

        Asynchronous handlers will have their coroutines kept for completion

        Args:
            event_name: The name of the event to trigger
            caller: Who is responsible for triggering the event
            *args: Positional arguments for the handlers
            **kwargs: Keyword arguments for the handlers
        """
        if not self.__fail_on_missing_event and event_name not in self.__events:
            return

        if event_name not in self.__events:
            raise ValueError(f"There are no registered handlers for the '{event_name}' event")

        handler_group, event, args, kwargs = self.__prepare_call(
            event_name=event_name,
            caller=caller,
            *args,
            **kwargs
        )

        awaitables = handler_group.trigger(event, *args, **kwargs)

        self.__active_awaitables.extend(
            awaitable
            for awaitable in awaitables
            if inspect.isawaitable(awaitable)
        )

    def __call__(self, event: typing.Union[str, Event], caller: _T, *args, **kwargs):
        """
        Call all handlers for a given event synchronously

        Asynchronous handlers will have their coroutines kept for completion

        Args:
            event_name: The name of the event to trigger
            caller: Who is responsible for triggering the event
            *args: Positional arguments for the handlers
            **kwargs: Keyword arguments for the handlers
        """
        self.trigger(event=event, caller=caller, *args, **kwargs)

    async def fire(self, event_name: str, caller: _T, *args, **kwargs):
        """
        Call all handlers for a given event asynchronously

        Asynchronous handlers will have their coroutines kept for completion

        Args:
            event_name: The name of the event to trigger
            caller: Who is responsible for triggering the event
            *args: Positional arguments for the handlers
            **kwargs: Keyword arguments for the handlers
        """
        if not self.__fail_on_missing_event and event_name not in self.__events:
            return

        if event_name not in self.__events:
            raise ValueError(f"There are no registered handlers for the '{event_name}' event")

        handler_group, event, args, kwargs = self.__prepare_call(
            event_name=event_name,
            caller=caller,
            *args,
            **kwargs
        )

        await handler_group.fire(event, *args, **kwargs)
