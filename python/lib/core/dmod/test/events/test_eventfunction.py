"""
Tests for dmod.core.events.EventFunction
"""
from __future__ import annotations

import sys
import typing
import unittest
import inspect
import collections.abc as abstract_collections

from ...core.events.base_function import EventFunctionParameter
from ...core.events.base_function import EventFunction
from ...core.events.base_function import Event

EVENT = Event("click", caller=sys.modules[__name__])
ARG1 = 1
ARG2 = 4
ARG3 = True
ARG4 = False
ARG5 = "String"

ASYNC_TEST_FUNCTION_RESULT = 14
TEST_FUNCTION_RESULT = 4
ASYNC_METHOD_RESULT = 8
METHOD_RESULT = 2


async def async_test_function(event: Event, arg1: int, arg2: int, *args, **kwargs):
    return ASYNC_TEST_FUNCTION_RESULT


def test_function(event: Event, arg1: int, arg2: int, *args, **kwargs):
    return TEST_FUNCTION_RESULT


class TestEventFunction(unittest.IsolatedAsyncioTestCase):
    async def async_method(self, event: Event, arg1: int, arg2: int, *args, **kwargs):
        return ASYNC_METHOD_RESULT

    def method(self, event: Event, arg1: int, arg2: int, *args, **kwargs):
        return METHOD_RESULT

    async def test_eventfunction(self):
        async_test_eventfunction = EventFunction(async_test_function)
        test_eventfunction = EventFunction(test_function)
        async_method_eventfunction = EventFunction(self.async_method)
        method_eventfunction = EventFunction(self.method)

        self.assertTrue(async_test_eventfunction.is_async)
        self.assertFalse(test_eventfunction.is_async)
        self.assertTrue(async_method_eventfunction.is_async)
        self.assertFalse(method_eventfunction.is_async)

        async_test_eventfunction_result = async_test_eventfunction(EVENT, ARG1, ARG2, ARG3, ARG4, arg5=ARG5)
        self.assertTrue(inspect.isawaitable(async_test_eventfunction_result))

        async_test_eventfunction_result = await async_test_eventfunction_result

        self.assertEqual(async_test_eventfunction_result, ASYNC_TEST_FUNCTION_RESULT)

        test_eventfunction_result = test_eventfunction(EVENT, ARG1, ARG2, ARG3, ARG4, arg5=ARG5)
        self.assertFalse(inspect.isawaitable(test_eventfunction_result))

        self.assertEqual(test_eventfunction_result, TEST_FUNCTION_RESULT)

        async_method_eventfunction_result = async_method_eventfunction(EVENT, ARG1, ARG2, ARG3, ARG4, arg5=ARG5)
        self.assertTrue(inspect.isawaitable(async_method_eventfunction_result))

        async_method_eventfunction_result = await async_method_eventfunction_result

        self.assertEqual(async_method_eventfunction_result, ASYNC_METHOD_RESULT)

        method_eventfunction_result = method_eventfunction(EVENT, ARG1, ARG2, ARG3, ARG4, arg5=ARG5)
        self.assertFalse(inspect.isawaitable(method_eventfunction_result))

        self.assertEqual(method_eventfunction_result, METHOD_RESULT)

    async def test_evenfunctionparameter(self):
        first = EventFunctionParameter(index=0, name="first", type=str, required=True)
        second = EventFunctionParameter(index=9, name="second", type=typing.Union[str, int, bool], required=True)
        third = EventFunctionParameter(index=1, name="third", type=typing.Literal['cheese'], required=True)
        fourth = EventFunctionParameter(index=3, name="fourth", required=True)
        fifth = EventFunctionParameter(index=5, name="fifth", type=typing.Sized, required=True)
        sixth = EventFunctionParameter(index=8, name="sixth", type=typing.Sequence, required=True)
        seventh = EventFunctionParameter(index=32234, name="seventh", type=typing.Sequence[str], required=True)
        eighth = EventFunctionParameter(index=32, name="eighth", type=list, required=True)
        ninth = EventFunctionParameter(index=12, name="ninth", type=typing.List[typing.Union[str, int]], required=True)
        args = EventFunctionParameter(index=0, name="args", is_args=True)
        typed_args = EventFunctionParameter(index=93, name="typed_args", is_args=True, type=str)
        kwargs = EventFunctionParameter(index=1, name="kwargs", is_kwargs=True)

        first_types = first.acceptable_types
        self.assertEqual(first_types, {str})

        second_types = second.acceptable_types
        self.assertEqual(second_types, {str, int, bool})

        third_types = third.acceptable_types
        self.assertEqual(third_types, {str})

        fourth_types = fourth.acceptable_types
        self.assertIsNone(fourth_types, None)

        fifth_types = fifth.acceptable_types
        self.assertEqual(fifth_types, {typing.Sized})

        sixth_types = sixth.acceptable_types
        self.assertEqual(sixth_types, {typing.Sequence})

        seventh_types = seventh.acceptable_types
        self.assertEqual(seventh_types, {typing.Sequence})

        eighth_types = eighth.acceptable_types
        self.assertEqual(eighth_types, {list})

        ninth_types = ninth.acceptable_types
        self.assertEqual(ninth_types, {typing.List})

        args_types = args.acceptable_types
        self.assertIsNone(args_types)

        typed_args_types = typed_args.acceptable_types
        self.assertEqual(typed_args_types, {str})

        kwargs_types = kwargs.acceptable_types
        self.assertIsNone(kwargs_types)
