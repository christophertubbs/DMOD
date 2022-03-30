import unittest
import typing

from ..evaluations.specification import model
from .common import TestConstruction


class TestLocationSpecificationConstruction(TestConstruction):
    @classmethod
    def make_assertion_for_single_definition(
            cls,
            test: TestConstruction,
            parameters: typing.Dict[str, typing.Any],
            definition: model.LocationSpecification
    ):
        test.assertEqual(definition.should_identify, parameters['identify'])
        test.assertEqual(definition.from_field, parameters['from_field'])
        test.assertEqual(definition.pattern, parameters['pattern'])

        if "ids" in parameters:
            test.assertEqual(len(definition.ids), len(parameters['ids']))

            for id in parameters['ids']:
                test.assertIn(id, definition.ids)

        for key in parameters['properties']:
            test.assertIn(key, definition)
            test.assertEqual(definition[key], parameters['properties'][key])
            test.assertEqual(definition.properties[key], parameters['properties'][key])
            test.assertEqual(definition.get(key), parameters['properties'][key])

        test.assertIsNone(definition.get("NonExistentProperty"))
        test.assertTrue(definition.get("NonExistentProperty", True))

    def setUp(self) -> None:
        self.__params = {
            "identify": True,
            "from_field": "field",
            "pattern": "safsd*",
            "ids": [],
            "properties": {
                "prop5": 8,
                "property45": 16,
                "prope32": "test"
            }
        }

        self.__param_list = [
            {
                "identify": True,
                "from_field": "field",
                "pattern": "safsd*",
                "ids": [],
                "properties": {
                    "prop5": 8,
                    "property45": 16,
                    "prope32": "test"
                }
            },
            {
                "identify": True,
                "from_field": None,
                "pattern": None,
                "ids": [
                    "Fred",
                    "Ed",
                    "Trey",
                    "Mark",
                    "Tom",
                    "Russ",
                    "Darone"
                ],
                "properties": {
                    "prop1": 6,
                    "prop2": "one",
                    "prop3": False
                }
            },
            {
                "identify": False,
                "from_field": None,
                "pattern": None,
                "ids": [],
                "properties": {
                    "prop1": 1,
                    "prop2": 3,
                    "prop3": False
                }
            }
        ]

    @classmethod
    def get_model_to_construct(cls) -> typing.Type[model.Specification]:
        return model.LocationSpecification

    @property
    def params(self) -> typing.Dict[str, typing.Any]:
        return self.__params

    @property
    def param_list(self) -> typing.Sequence[typing.Dict[str, typing.Any]]:
        return self.__param_list


if __name__ == '__main__':
    unittest.main()