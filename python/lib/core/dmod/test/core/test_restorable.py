"""
Unit tests for dmod.core.restorable
"""
from __future__ import annotations

import inspect
import typing
import unittest

from dmod.core import restorable
from dmod.core.common import tasks


def handler_one(value: str) -> bool:
    """
    A simple function used to simulate an event handler. Returns True if the first character is an upper case character

    Args:
        value: A string to test

    Returns:
        True if the first character is an upper case character
    """
    return isinstance(value, str) and len(value) > 0 and value[0].isupper()


def handler_two(value: str) -> bool:
    """
    A simple function used to simulate an event handler. Returns True if the first character is a lower case character

    Args:
        value: A string to test

    Returns:
        True if the first character is a lower case character
    """
    return isinstance(value, str) and len(value) > 0 and value[0].islower()


def handler_three(value: str) -> bool:
    """
    A simple function used to simulate an event handler. Returns True if the string is longer than 3 characters

    Args:
        value: A string to test

    Returns:
        True if the string is longer than 3 characters
    """
    return isinstance(value, str) and len(value) > 3


def multiple_argument_function(value1: int = None, value2: int = None, value3: int = None):
    """
    A simple function that multiplies the first two numbers together and divides the result by the third

    Args:
        value1: The value to multiply by the second. 1 if value1 is None
        value2: The value to multiply by the first. 1 if value2 is None
        value3: The value to divide the product of value1 and value2 by. 1 if value3 is None or 0

    Returns:
        (value1 * value2) / value3
    """
    if value1 is None:
        value1 = 1

    if value2 is None:
        value2 = 1

    if value3 in (None, 0):
        value3 = 1

    return value1 * value2 / value3


class EventBus(restorable.Restorable):
    """
    An example `Restorable` class used to show that an implementation behaves as expected
    """
    @classmethod
    def give_value(cls):
        """
        An example class function that may be called by an outside entity

        Returns:
            A random integer between 0 and 99
        """
        import random
        return random.randrange(0, 99)

    def __init__(
        self,
        example_function: typing.Callable[[], int],
        handlers: typing.Dict[str, typing.List[typing.Callable]]
    ):
        self.example_function = example_function
        self.handlers = handlers

    def get_package_arguments(self) -> typing.List:
        return []

    def get_package_keyword_arguments(self) -> typing.Dict[str, typing.Any]:
        return {
            "example_function": restorable.PackagedRestorable.from_function(self.example_function),
            "handlers": {
                event: [
                    restorable.PackagedRestorable.from_function(handler)
                    for handler in event_handlers
                ]
                for event, event_handlers in self.handlers.items()
            }
        }


class TestRestorable(unittest.TestCase):
    """
    Unit tests for dmod.core.restorable
    """
    def test_restoredpackage(self):
        """
        Tests to see if RestoredPackage behaves as expected
        """
        restored_package = restorable.RestoredPackage.create(**{
            "module": "dmod.core.common.tasks",
            "name": "CancelResults",
            "arguments": ["Steve", False],
            "keyword_arguments": {
                "message": "message"
            }
        })
        simple_task: tasks.CancelResults = restored_package()

        self.assertFalse(simple_task.cancelled)
        self.assertEqual(simple_task.message, "message")
        self.assertEqual(simple_task.task_name, "Steve")

        restored_package = restorable.RestoredPackage.create(**{
            "module": "dmod.core.common.tasks",
            "name": "CancelResults",
            "arguments": [False]
        })
        mild_task: tasks.CancelResults = restored_package("Steve", message="message")

        self.assertFalse(mild_task.cancelled)
        self.assertEqual(mild_task.message, "message")
        self.assertEqual(mild_task.task_name, "Steve")

        self.assertEqual(mild_task, simple_task)

        complex_definition = {
            "module": "dmod.core.common.tasks",
            "name": "CancelResults",
            "arguments": [
                {
                    "module": "dmod.core.common.helper_functions",
                    "name": "humanize_text",
                    "keyword_arguments": {
                        "text": "steREMOVE THISve",
                        "exclude_phrases": "REMOVE THIS"
                    }
                }
            ],
            "keyword_arguments": {
                "cancelled": {
                    "module": "dmod.core.common",
                    "name": "is_true",
                    "arguments": ["negatory"]
                }
            }
        }

        restored_package = restorable.RestoredPackage.create(**complex_definition)
        complex_task: tasks.CancelResults = restored_package(message="message")

        self.assertFalse(complex_task.cancelled)
        self.assertEqual(complex_task.message, "message")
        self.assertEqual(complex_task.task_name, "Steve")

        self.assertEqual(simple_task, complex_task)

        wrapped_complex_definition = {
            "module": "dmod.core.restorable",
            "name": "RestoredPackage",
            "keyword_arguments": complex_definition
        }

        wrapped_complex_definition['keyword_arguments']['keyword_arguments']['message'] = 'message'

        restored_package = restorable.RestoredPackage.create(**wrapped_complex_definition)
        super_complex_task: tasks.CancelResults = restored_package()

        self.assertFalse(super_complex_task.cancelled)
        self.assertEqual(super_complex_task.message, "message")
        self.assertEqual(super_complex_task.task_name, "Steve")

        self.assertEqual(simple_task, super_complex_task)

        restored_package_module_name = inspect.getmodule(restorable.RestoredPackage).__name__
        restored_package_name = restorable.RestoredPackage.__name__

        wrapped_wrapped_complex_definition = {
            "module": restored_package_module_name,
            "name": restored_package_name,
            "keyword_arguments": wrapped_complex_definition
        }

        restored_package = restorable.RestoredPackage.create(**wrapped_wrapped_complex_definition)
        ultra_complex_task: tasks.CancelResults = restored_package()

        self.assertFalse(ultra_complex_task.cancelled)
        self.assertEqual(ultra_complex_task.message, "message")
        self.assertEqual(ultra_complex_task.task_name, "Steve")

        self.assertEqual(simple_task, ultra_complex_task)

        function_definition = {
            "module": "test_restorable",
            "name": handler_one.__name__,
            "is_function": True
        }
        restored_function = restorable.RestoredPackage.create(**function_definition)
        self.assertTrue(restored_function("SFFSSFS"))

        fully_defined_function_definition = {
            "module": "test_restorable",
            "name": multiple_argument_function.__name__,
            "arguments": [
                4,
                5,
                2
            ]
        }

        restored_function = restorable.RestoredPackage.create(**fully_defined_function_definition)
        self.assertEqual(restored_function(), 10)

        partially_defined_function_definition = {
            "module": "test_restorable",
            "name": multiple_argument_function.__name__,
            "arguments": [
                5,
            ],
            "keyword_arguments": {
                "value3": 2
            }
        }

        restored_function = restorable.RestoredPackage.create(**partially_defined_function_definition)
        self.assertEqual(restored_function(4), 10)

        minimally_defined_function_definition = {
            "module": "test_restorable",
            "name": multiple_argument_function.__name__,
            "keyword_arguments": {
                "value2": 5
            }
        }

        restored_function = restorable.RestoredPackage.create(**minimally_defined_function_definition)
        self.assertEqual(restored_function(4, value3=2), 10)





    def test_packagedrestorable(self):
        bus = EventBus(
            example_function=EventBus.give_value,
            handlers={
                "one": [
                    handler_one
                ],
                "two": [
                    handler_two
                ],
                "three": [
                    handler_two,
                    handler_three
                ]
            }
        )

        packaged_bus = bus.create_restorable_package()
        self.assertIsNotNone(packaged_bus)

        try:
            packaged_bus.dict()
        except:
            self.fail("A RestorablePackage could not be converted into a dictionary")

        try:
            packaged_bus.json(indent=4)
        except:
            self.fail("A RestorablePackage could not be serialized into JSON")

        restored_bus: EventBus = packaged_bus.restore()
        self.assertIsInstance(restored_bus, EventBus)
        self.assertIsInstance(restored_bus.example_function(), int)

        handler_one_results = [
            value
            for value in map(lambda handler: handler("Steve"), restored_bus.handlers['one'])
        ]
        self.assertEqual(len(handler_one_results), 1)
        self.assertEqual(handler_one_results, [True])

        handler_two_results = [
            value
            for value in map(lambda handler: handler("Steve"), restored_bus.handlers['two'])
        ]
        self.assertEqual(len(handler_two_results), 1)
        self.assertEqual(handler_two_results, [False])

        handler_three_results = [
            value
            for value in map(lambda handler: handler("Steve"), restored_bus.handlers['three'])
        ]
        self.assertEqual(len(handler_three_results), 2)
        self.assertEqual(handler_three_results, [False, True])

    def test_restorablefield(self):
        is_true = restorable.RestorableField(
            field_module="dmod.core.common",
            field_name="is_true",
            args=["true"]
        )

        self.assertTrue(is_true())

        packaged_is_true = is_true.create_restorable_package()
        value_from_packaged_is_true = packaged_is_true.restore()

        expected_package = {
            "module": "dmod.core.common",
            "name": "is_true",
            "arguments": ["true"],
            "keyword_arguments": {}
        }

        restored_is_true = restorable.restore_value(expected_package)

        self.assertEqual(is_true(), restored_is_true)

        restored_field_spec = {
            "module": "dmod.core.restorable",
            "name": "RestorableField",
            "keyword_arguments": {
                "field_module": "dmod.core.common",
                "field_name": 'is_true',
                "arguments": ['true']
            }
        }

        restored_from_spec = restorable.restore_value(restored_field_spec)

        self.assertEqual(is_true, restored_from_spec)
        self.assertEqual(is_true(), restored_from_spec())
