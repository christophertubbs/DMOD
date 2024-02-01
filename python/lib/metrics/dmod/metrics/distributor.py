"""
Provides a mechanism for instructing a system on how to perform a repetitive task with different sets of parameters

While the implementations are here aren't special, more advanced work distribution classes may submit work to
other services, environments, processes, applications, etc. The intent is to include a distribution implementation
that may farm tasks out to redis.
"""
from __future__ import annotations

import inspect
import typing
import asyncio
import itertools

from typing_extensions import ParamSpec

ARGS_AND_KWARGS = ParamSpec("ARGS_AND_KWARGS")

RESULT_TYPE = typing.TypeVar("RESULT_TYPE")

SynchronousWorkFunction = typing.Callable[[ARGS_AND_KWARGS], RESULT_TYPE]
AsynchronousWorkFunction = typing.Callable[[ARGS_AND_KWARGS], typing.Awaitable[RESULT_TYPE]]

WorkFunction = typing.Union[
    SynchronousWorkFunction,
    AsynchronousWorkFunction,
    typing.Sequence[SynchronousWorkFunction],
    typing.Sequence[AsynchronousWorkFunction]
]

WorkFunctionPayload = typing.Dict[str, typing.Any]


@typing.runtime_checkable
class WorkDistributionProtocol(typing.Protocol):
    def perform(
        self,
        function: typing.Union[SynchronousWorkFunction, typing.Iterable[SynchronousWorkFunction]],
        parameters: typing.Iterable[WorkFunctionPayload],
        *common_args,
        **common_kwargs
    ) -> typing.Sequence[RESULT_TYPE]:
        ...

    async def perform_asynchronously(
        self,
        function: WorkFunction,
        parameters: typing.Iterable[WorkFunctionPayload],
        *common_args,
        **common_kwargs
    ) -> typing.Sequence[RESULT_TYPE]:
        ...


class SynchronousWorkDistributor(WorkDistributionProtocol):
    def perform(
        self,
        function: typing.Union[SynchronousWorkFunction, typing.Iterable[SynchronousWorkFunction]],
        parameters: typing.Iterable[WorkFunctionPayload],
        *common_args,
        **common_kwargs
    ) -> typing.Sequence[RESULT_TYPE]:
        for kwargs in parameters:
            kwargs.update({
                key: value
                for key, value in common_kwargs.items()
                if key not in kwargs
            })

        if isinstance(function, typing.Callable):
            results = [
                function(*common_args, **kwargs)
                for kwargs in parameters
            ]
        elif isinstance(function, typing.Iterable):
            non_functions = [
                item
                for item in function
                if not isinstance(item, typing.Callable)
            ]

            if non_functions:
                non_function_descriptions = ', '.join([
                    f"{non_function}: ({type(non_function)})"
                    for non_function in non_functions
                ])

                raise TypeError(
                    f"Cannot call non-callable objects: {non_function_descriptions}"
                )

            results = [
                func(*common_args, **kwargs)
                for func, kwargs in itertools.product(function, parameters)
            ]
        else:
            raise TypeError(
                f"Cannot run function(s) - "
                f"'{function} ({type(function)}' is not valid input used to instruct the distributor as to what to do"
            )

        return [result for result in results]

    async def perform_asynchronously(
        self,
        function: WorkFunction,
        parameters: typing.Iterable[WorkFunctionPayload],
        *common_args,
        **common_kwargs
    ) -> typing.Sequence[RESULT_TYPE]:
        raise NotImplementedError("Synchronous work distributors cannot perform asynchronous actions")


class ThreadedWorkDistributor(WorkDistributionProtocol):
    def perform(
        self,
        function: typing.Union[SynchronousWorkFunction, typing.Iterable[SynchronousWorkFunction]],
        parameters: typing.Iterable[WorkFunctionPayload],
        *common_args,
        **common_kwargs
    ) -> typing.Sequence[RESULT_TYPE]:
        raise NotImplementedError("Threaded work distributors do not perform synchronous actions")

    def _call_asynchronous_function(
        self,
        function: typing.Union[SynchronousWorkFunction, AsynchronousWorkFunction],
        *args,
        **kwargs
    ) -> typing.Awaitable[RESULT_TYPE]:
        if not isinstance(function, typing.Callable):
            raise TypeError(
                f"Cannot schedule an asynchronous function call for '{function}: ({type(function)})'; "
                f"it is not callable"
            )

        if inspect.iscoroutinefunction(function):
            return function(*args, **kwargs)

        return asyncio.to_thread(function, *args, **kwargs)

    async def perform_asynchronously(
        self,
        function: WorkFunction,
        parameters: typing.Iterable[WorkFunctionPayload],
        *common_args,
        **common_kwargs
    ) -> typing.Sequence[RESULT_TYPE]:
        results: typing.List[RESULT_TYPE] = []

        for kwargs in parameters:
            kwargs.update({
                key: value
                for key, value in common_kwargs.items()
                if key not in kwargs
            })

        if isinstance(function, typing.Callable):
            async_results = [
                self._call_asynchronous_function(function, *common_args, **kwargs)
                for kwargs in parameters
            ]
        elif isinstance(function, typing.Iterable):
            non_functions = [
                item
                for item in function
                if not isinstance(item, typing.Callable)
            ]

            if non_functions:
                non_function_descriptions = ', '.join([
                    f"{non_function}: ({type(non_function)})"
                    for non_function in non_functions
                ])

                raise TypeError(
                    f"Cannot call non-callable objects: {non_function_descriptions}"
                )

            async_results = [
                self._call_asynchronous_function(func, *common_args, **kwargs)
                for func, kwargs in itertools.product(function, parameters)
            ]
        else:
            raise TypeError(
                f"Cannot run function(s) - "
                f"'{function} ({type(function)}' is not valid input used to instruct the distributor as to what to do"
            )

        results.extend([
            result
            for result in async_results
            if not inspect.isawaitable(result)
        ])

        async_results = [
            result
            for result in async_results
            if inspect.isawaitable(result)
        ]

        results.extend(await asyncio.gather(*async_results))
        return results
