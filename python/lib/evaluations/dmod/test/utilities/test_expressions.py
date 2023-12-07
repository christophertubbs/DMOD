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
            " <% '5' + '6' %>": expressions.ExtractedExpression(
                value_one="5",
                value_two="6",
                operator="+"
            ),
            "<%'5'-'6'%>": expressions.ExtractedExpression(
                value_one="5",
                value_two="6",
                operator="-"
            ),
            "<% 'one two three four': list      get '5' %>  ": expressions.ExtractedExpression(
                value_one="one two three four",
                value_two="5",
                operator="get",
                value_one_cast="list"
            ),
            "<% '-2342342234.23':path.to.some_class path.to.some.operation 'sdfosdf':slice%>": expressions.ExtractedExpression(
                value_one='-2342342234.23',
                value_two='sdfosdf',
                operator="path.to.some.operation",
                value_one_cast="path.to.some_class",
                value_two_cast="slice"
            ),
            "<% 'abc':<% 'types_of values' get    '3':int%> ?? 'True':bool%>": expressions.ExtractedExpression(
                value_one="types_of values",
                value_two="3",
                operator="get",
                value_two_cast="int"
            ),
        }

        values_without_expressions = [
            " <% '5' + '6 %>",
            " <% 5 + 6 %>",
            " <% '5'  '6' %>",
            "<% 'abc':<% 'types_of values' get    '3':int> ?? 'True':bool%>",
            "<% '-2342'342234.23':path.to.some_class path.to.some.operation 'sdfosdf':slice%>",
            "<% '-2342342234.23':path.to.some_class path.to.some.operation 'sdfosdf':slic e%>",
            "<% '-2342342234.23':path.to.some_class path.to.some.operation 'sdfosdf':slice>"
            "<% '-2342342234.23':path.to.some_class path.to.some.operation 'sdfosdf':slice"
        ]

        for expression, expected_value in values_with_expressions.items():
            extracted_values = expressions.extract_expression(expression)
            self.assertEqual(extracted_values, expected_value)

        self.assertTrue(not any(map(expressions.extract_expression, values_without_expressions)))

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

    def test_process_expressions(self):
        self.fail("Test not implemented")

    def test_available_modules(self):
        self.fail("Test not implemented")