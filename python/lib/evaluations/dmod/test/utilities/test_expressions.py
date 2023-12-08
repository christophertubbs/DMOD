"""
Tests for dmod.evaluations.utilities.expressions
"""
from __future__ import annotations

import typing
from unittest import TestCase

from ...evaluations.utilities import expressions


class ExpressionTests(TestCase):
    def test_extract_variable_name(self):
        """
        Tests to ensure that the `VariablePattern` regular expression works as intended
        """
        values_with_variables = {
            "{{% variable_one %}}": "variable_one",
            "{{%variable_two %}}": "variable_two",
            "{{%variable_three%}}": "variable_three",
            "   {{% variable_four %}}    ": "variable_four",
            " {{% variable_five%}}/path": "variable_five",
            "{{% variable_six %}} + {{% variable_seven %}}": "variable_six"
        }

        values_without_variables = [
            "{{ variable_name }}",
            "{ {% variable_name %}}"
            "{{% variable_name }}"
            "{% variable_name %}"
        ]

        for input_value, expected_value in values_with_variables.items():
            variable_name = expressions.extract_variable_name(input_value)
            self.assertEqual(variable_name, expected_value)

        for value in values_without_variables:
            variable_name = expressions.extract_variable_name(value)
            self.assertIsNone(variable_name)
    
    def test_extract_expression(self):
        """
        Tests to ensure that the `ExpressionPattern` regular expression works as intended
        """
        values_with_expressions = {
            " <% `5` + `6` %>": expressions.ExtractedExpression(
                value_one="5",
                value_two="6",
                operator="+"
            ),
            "<%`5`-`6`%>": expressions.ExtractedExpression(
                value_one="5",
                value_two="6",
                operator="-"
            ),
            "<% `one two three four`: list      get `5` %>  ": expressions.ExtractedExpression(
                value_one="one two three four",
                value_two="5",
                operator="get",
                value_one_cast="list"
            ),
            "<% `-2342342234.23`:path.to.some_class path.to.some.operation `sdfosdf`:slice%>": expressions.ExtractedExpression(
                value_one='-2342342234.23',
                value_two='sdfosdf',
                operator="path.to.some.operation",
                value_one_cast="path.to.some_class",
                value_two_cast="slice"
            ),
            "<% `abc`:<% `types_of values` get    `3`:int%> ?? `True`:bool%>": expressions.ExtractedExpression(
                value_one="types_of values",
                value_two="3",
                operator="get",
                value_two_cast="int"
            ),
        }

        values_without_expressions = [
            " <% 5` + `6 %>",
            "<% '5' + '6' %>",
            " <% 5 + 6 %>",
            " <% `5`  `6` %>",
            "<% `abc`:<% `types_of values` get    `3`:int> ?? `True`:bool%>",
            "<% `-2342`342234.23`:path.to.some_class path.to.some.operation `sdfosdf`:slice%>",
            "<% `-2342342234.23`:path.to.some_class path.to.some.operation `sdfosdf`:slic e%>",
            "<% `-2342342234.23`:path.to.some_class path.to.some.operation 'sdfosdf':slice>"
            "<% `-2342342234.23`:path.to.some_class path.to.some.operation `sdfosdf`:slice"
        ]

        for expression, expected_value in values_with_expressions.items():
            extracted_values = expressions.extract_expression(expression)
            self.assertEqual(extracted_values, expected_value)

        self.assertTrue(not any(map(expressions.extract_expression, values_without_expressions)))

    def test_interpret_map(self):
        same_maps = [
            '{'
            '"one": 1, '
            '"two": -2, '
            '"three": 3.234, '
            '"four": -4.2342, '
            '"five": false, '
            '"six": true, '
            '"seven": null, '
            '"eight":  {'
            '"one": 1, '
            '"two": -2, '
            '"three": 3.234, '
            '"four": -4.2342, '
            '"five": false, '
            '"six": true, '
            '"seven": null'
            '}'
            '}',
            '"one": 1, '
            '"two": -2, '
            '"three": 3.234, '
            '"four": -4.2342, '
            '"five": false, '
            '"six": true, '
            '"seven": null, '
            '"eight":  {'
            '"one": 1, '
            '"two": -2, '
            '"three": 3.234, '
            '"four": -4.2342, '
            '"five": false, '
            '"six": true, '
            '"seven": null'
            '}',
            '{'
            '"one": 1 '
            '"two": -2 '
            '"three": 3.234 '
            '"four": -4.2342 '
            '"five": false '
            '"six": true '
            '"seven": null '
            '"eight":  {'
            '"one": 1 '
            '"two": -2 '
            '"three": 3.234 '
            '"four": -4.2342 '
            '"five": false '
            '"six": true '
            '"seven": null'
            '}'
            '}',
            '"one": 1 '
            '"two": -2 '
            '"three":   3.234 '
            '"four": -4.2342 '
            '"five":        false '
            '"six": true '
            '"seven": null '
            '"eight":   {'
            '"one":     1        '
            '"two": -2 '
            '"three": 3.234 '
            '"four": -4.2342 '
            ' "five": false '
            '"six":     true '
            '"seven":   null'
            '}',
            '{'
            "'one': 1, "
            "'two': -2, "
            "'three': 3.234, "
            "'four': -4.2342, "
            '"five": false, '
            '"six": true, '
            '"seven": null, '
            "'eight':  {"
            '"one": 1, '
            '"two": -2, '
            "'three': 3.234, "
            '"four": -4.2342, '
            '"five": false, '
            '"six": true, '
            '"seven": null'
            '}'
            '}',
        ]

        expected_map = {
            "one": 1,
            "two": -2,
            "three": 3.234,
            "four": -4.2342,
            "five": False,
            "six": True,
            "seven": None,
            "eight": {
                "one": 1,
                "two": -2,
                "three": 3.234,
                "four": -4.2342,
                "five": False,
                "six": True,
                "seven": None,
            }
        }

        for map_string in same_maps:
            generated_map = expressions.interpret_map(map_string=map_string)
            self.assertEqual(expected_map, generated_map)

        self.assertEqual(
            expressions.interpret_map(map_string='{"one": 1, "2": "two"}'),
            {"one": 1, "2": "two"}
        )

    def test_transform_tree(self):
        self.fail("Test not implemented")

    def test_transform_sequence(self):
        self.fail("Test not implemented")

    def test_perform_operation(self):
        self.fail("Test not implemented")

    def test_value_to_sequence(self):
        self.fail("Test not implemented")

    def test_to_slice(self):
        self.fail("Test not implemented")

    def test_cast_value(self):
        self.fail("Test not implemented")

    def test_evaluate_expression(self):
        self.fail("Test not implemented")

    def test_transform_value(self):
        self.fail("Test not implemented")

    def test_create_variables_for_use(self):
        self.fail("Test not implemented")

    def test_should_replace_variable(self):
        self.fail("Test not implemented")

    def test_apply_variable(self):
        self.fail("Test not implemented")

    def test_search_for_and_apply_variables(self):
        self.fail("Test not implemented")

    def test_is_expression(self):
        self.fail("Test not implemented")

    def test_search_for_and_apply_expressions(self):
        self.fail("Test not implemented")

    def test_add_to(self):
        """
        Test to make sure that the add operation correctly adds values and correctly considers if strings are
        supposed to be collections or numbers
        """
        add = expressions.add_to

        self.assertEqual(add({"one": 1}, {"two": 2}), {"one": 1, "two": 2})
        self.assertEqual(add('-13', '7'), -6)
        self.assertEqual(add('-13', 7), -6)
        self.assertEqual(add(-13, '7'), -6)
        self.assertEqual(add(-13, 7), -6)
        self.assertEqual(add({1, 2, 3}, 3), {1, 2, 3})
        self.assertEqual(add({1, 2, 3}, {3, 4, 5}), {1, 2, 3, 4, 5})
        self.assertEqual(add([1, 2, 3], 3), [1, 2, 3, 3])
        self.assertEqual(add([1, 2, 3], '1,2,3,4'), [1, 2, 3, 1, 2, 3, 4])
        self.assertEqual(add('1, 2, 3, 4', [1, 2, 3]), [1, 2, 3, 4, 1, 2, 3])
        self.assertEqual(add((1, 2, 3), [1, 2, 3]), [1, 2, 3, 1, 2, 3])
        self.assertEqual(add([1, 2, 3], [1, 2, 3]), [1, 2, 3, 1, 2, 3])
        self.assertEqual(add(3, {1, 2, 3}), {1, 2, 3})
        self.assertEqual(add(True, False), 1)
        self.assertEqual(add(False, False), 0)
        self.assertEqual(add(True, True), 2)
        self.assertEqual(add(1, "one"), "1one")
        self.assertEqual(add("one", 1), "one1")
        self.assertEqual(add("one", "1"), "one1")

        self.assertAlmostEqual(add('-13.123', '7'), -6.1229, places=3)
        self.assertAlmostEqual(add('-13.123', 7), -6.1229, places=3)
        self.assertAlmostEqual(add(-13.123, '7'), -6.1229, places=3)
        self.assertAlmostEqual(add(-13.123, 7), -6.1229, places=3)

        self.assertEqual(add('-13', '7.456'), -5.544)
        self.assertEqual(add('-13', 7.456), -5.544)
        self.assertEqual(add(-13, '7.456'), -5.544)
        self.assertEqual(add(-13, 7.456), -5.544)

    def test_getitem(self):
        """
        Test the 'get' operation
        """
        self.assertEqual(expressions.get_item({"one": 1, 2: "two"}, 2), "two")
        self.assertEqual(expressions.get_item({"one": 1, '2': "two"}, 2), "two")
        self.assertEqual(expressions.get_item({"one": 1, '2': "two"}, '2'), "two")
        self.assertEqual(expressions.get_item('{"one": 1, "2": "two"}', 2), "two")
        self.assertEqual(expressions.get_item('{"one": 1, "2": "two"}', '2'), "two")
        self.assertEqual(expressions.get_item([1, "two"], '1'), "two")
        self.assertEqual(expressions.get_item([1, "two"], 1), "two")
        self.assertEqual(expressions.get_item([1, "two"], 1.15215148), "two")
        self.assertEqual(expressions.get_item('1, "two"', '1'), "two")
        self.assertEqual(expressions.get_item('1, "two"', 1), "two")
        self.assertEqual(expressions.get_item('1, "two"', 1.15215148), "two")
        self.assertEqual(expressions.get_item('1 | "two"', '1'), "two")
        self.assertEqual(expressions.get_item('1 |"two"', 1), "two")
        self.assertEqual(expressions.get_item('1| "two"', 1.15215148), "two")

    def test_multiply(self):
        multiply = expressions.multiply
        self.assertEqual(multiply("test", 2), "testtest")
        self.assertEqual(multiply("test", '2'), "testtest")
        self.assertEqual(multiply(5, 5), 25)
        self.assertEqual(multiply('5', 5), 25)
        self.assertEqual(multiply(5, '5'), 25)
        self.assertEqual(multiply('5', '5'), 25)
        self.assertEqual(multiply('0.5', -10), -5)
        self.assertEqual(multiply('0.5', '-10'), -5)
        self.assertEqual(multiply('-0.5', '-10'), 5)
        self.assertEqual(multiply("1,   2, 3,   ,4,5   , 6", 2), [1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6])

    def test_expressionoperators(self):
        operators = expressions.ExpressionOperator
        self.assertEqual(operators["+"](1, 1), 2)
        self.assertEqual(operators["+"](True, False), 1)
        self.assertEqual(operators["+"]("one", "two"), "onetwo")
        self.assertEqual(operators['get']([1, 2, 3, 4], 1), 2)
        self.assertEqual(operators['get']({'one': 1, "two": 2}, 'two'), 2)
        self.assertEqual(operators['get']("{'one': 1, \"two\": 2}", 'two'), 2)
        self.assertEqual(operators['get']([1, 2, 3, 4], "1"), 2)
        self.assertEqual(operators['get']({'one': 1, "two": 2}, 'two'), 2)
        self.assertEqual(operators["get"]("one", 1), 'n')
        self.assertEqual(operators["get"]("one,two,three", 2), "three")
        self.assertEqual(operators['get']("one,two,three", '2'), "three")
        self.assertEqual(operators["??"]("", 5), 5)
        self.assertEqual(operators["??"](5, ""), 5)
        self.assertEqual(operators["??"](5, 234234), 5)
        self.assertEqual(operators['??']([], 0), 0)
        self.assertEqual(operators['??'](None, []), [])
        self.assertEqual(operators['??']([], None), None)
        self.assertEqual(operators['??'](0, []), [])

    def test_process_expressions(self):
        new_variable_key = "varKey"
        tree_one = {
            new_variable_key: {
                "value_1": 38,
                "value_2": 2342,
                "location": "sweden",
                "list": [1, 2, 3, 4],
                "boolean value": False,
                "hex_list": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, "A", "B", "C", "D", "E", "F"],
                "floating point": -23.2342235224,
                "string list": "1|2|3|4",
                "nested_values": {
                    "unit": "cms",
                    "measurement": -2342.234,
                    "location": "{{% location %}}",
                    "tracking": "<% `boolean value` ?? `13432` %>"
                }
            },
            "country": "{{%  location%}}",
            "nest": {
                "time": "<% `NOW NAIVE` + `-0000`%>",
                "v": "<% `value_2` / `value_1` %>",
                "t": "<% `nested_values` get `tracking` %>"
            },
            "collection": [
                {
                    "hex": "<% `hex_list` get `11`:int %>",
                    "number": "<% `list` get `3`%>",
                    "fp": "{{% floating point %}}",
                    "nv": "<% `<% `nested_values` get `measurement` %>` / `100.0` %>"
                },
                {
                    "hex": "<% `hex_list` get `0|3`:slice %>",
                    "number": "<% `string list` get `2`%>",
                    "fp": "<% `floating point` * `-12` %>",
                    "nv": "{{% nested_values %}}"
                },
                {
                    "hex": "<% `hex_list` get `1,13,5`:slice%>",
                    "number": "<% `string list` get '0'%>",
                    "fp": "<% `floating point` / `7` %>",
                    "nv": "<% `5` * `value_1`:float%>"
                }
            ]
        }

        changed_values = expressions.process_expressions(data=tree_one, new_variable_key=new_variable_key)
        self.assertGreater(changed_values, 0)

    def test_available_modules(self):
        self.fail("Test not implemented")