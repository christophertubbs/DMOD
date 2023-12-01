import unittest
import typing

from ..evaluations.util import RelativeDuration


class RelativeDurationTest(unittest.TestCase):
    """
    Tests to ensure that the `RelativeDuration` class behaves as expected

    Terms:

    - 'convoluted_duration': a convoluted duration is a duration whose inner values exceed their range
        - A convoluted duration may last 73 seconds, 90 minutes, 27 hours, 50 days, 15 months, etc
    """
    # 6 Hours
    short_normal_duration: typing.Final[RelativeDuration] = RelativeDuration.from_string("PT6H")

    # 3 Hours, 72 Minutes, 6480 Seconds - equivalent to 6 hours
    short_convoluted_duration: typing.Final[RelativeDuration] = RelativeDuration.from_string("PT3H72M6480S")

    # 1 Month, 3 Days, 6 hours
    medium_normal_duration: typing.Final[RelativeDuration] = RelativeDuration.from_string("P1M3DT6H")

    # 1 Month, 1 Day, 27 Hours, 1440 minutes, 95760 Seconds - equivalent to 1 Month, 3 days, 6 Hours
    medium_convoluted_duration: typing.Final[RelativeDuration] = RelativeDuration.from_string("P1M1DT27H1440M95760S")

    # 1 Year, 7 Months, 12 Days, 12 Hours
    long_normal_duration: typing.Final[RelativeDuration] = RelativeDuration.from_string("P1Y7M12DT12H")

    # 19 Months, 9 Days, 67 Hours, 980 Minutes, 2400 Seconds - equivalent to 1 Year, 7 Months, 12 Days, 12 Hours
    long_convoluted_duration: typing.Final[RelativeDuration] = RelativeDuration.from_string("P19M9DT67H980M2400S")

    def test_comparisons(self):
        """
        Checks to make sure the comparison operations behave as expected
        """
        self.assert_equal([self.short_normal_duration, self.short_convoluted_duration])
        self.assert_not_equal(
            [
                self.short_normal_duration,
                self.short_convoluted_duration
            ],
            [
                self.medium_normal_duration,
                self.medium_convoluted_duration,
                self.long_normal_duration,
                self.long_convoluted_duration
            ]
        )

        self.assert_equal([self.medium_normal_duration, self.medium_convoluted_duration])
        self.assert_not_equal(
            [
                self.medium_normal_duration,
                self.medium_convoluted_duration
            ],
            [
                self.short_normal_duration,
                self.short_convoluted_duration,
                self.long_normal_duration,
                self.long_convoluted_duration
            ]
        )

        self.assert_equal([self.long_normal_duration, self.long_convoluted_duration])
        self.assert_not_equal(
            [
                self.long_normal_duration,
                self.long_convoluted_duration
            ],
            [
                self.short_normal_duration,
                self.short_convoluted_duration,
                self.medium_normal_duration,
                self.medium_convoluted_duration,
            ]
        )

        self.assert_less(
            [
                self.short_normal_duration,
                self.short_convoluted_duration
            ],
            [
                self.medium_normal_duration,
                self.medium_convoluted_duration,
                self.long_normal_duration,
                self.long_convoluted_duration
            ]
        )

        self.assert_less_or_equal(
            [
                self.short_normal_duration,
                self.short_convoluted_duration
            ],
            [
                self.short_normal_duration,
                self.short_convoluted_duration,
                self.medium_normal_duration,
                self.medium_convoluted_duration,
                self.long_normal_duration,
                self.long_convoluted_duration
            ]
        )

        self.assert_less(
            [
                self.medium_normal_duration,
                self.medium_convoluted_duration
            ],
            [
                self.long_normal_duration,
                self.long_convoluted_duration
            ]
        )

        self.assert_less_or_equal(
            [
                self.medium_normal_duration,
                self.medium_convoluted_duration
            ],
            [
                self.medium_normal_duration,
                self.medium_convoluted_duration,
                self.long_normal_duration,
                self.long_convoluted_duration
            ]
        )

        self.assert_less(
            [
                self.long_normal_duration,
                self.long_convoluted_duration
            ],
            []
        )

        self.assert_less_or_equal(
            [
                self.long_normal_duration,
                self.long_convoluted_duration
            ],
            [
                self.long_normal_duration,
                self.long_convoluted_duration
            ]
        )

        self.assert_greater(
            [
                self.medium_normal_duration,
                self.medium_convoluted_duration
            ],
            [
                self.short_normal_duration,
                self.short_convoluted_duration,
            ]
        )

        self.assert_greater_or_equal(
            [
                self.medium_normal_duration,
                self.medium_convoluted_duration
            ],
            [
                self.short_normal_duration,
                self.short_convoluted_duration,
                self.medium_normal_duration,
                self.medium_convoluted_duration
            ]
        )

        self.assert_greater(
            [
                self.long_normal_duration,
                self.long_convoluted_duration
            ],
            [
                self.short_normal_duration,
                self.short_convoluted_duration,
                self.medium_normal_duration,
                self.medium_convoluted_duration
            ]
        )

        self.assert_greater_or_equal(
            [
                self.long_normal_duration,
                self.long_convoluted_duration
            ],
            [
                self.short_normal_duration,
                self.short_convoluted_duration,
                self.medium_normal_duration,
                self.medium_convoluted_duration,
                self.long_normal_duration,
                self.long_convoluted_duration
            ]
        )

    def assert_equal(self, values: typing.Sequence[RelativeDuration]):
        if not isinstance(values, typing.Sequence):
            values = [values]

        for value_index in range(len(values)):
            value = values[value_index]
            self.assertEqual(value, value)
            for other_index in range(len(values)):
                if value_index == other_index:
                    continue
                other_value = values[other_index]
                self.assertEqual(value, other_value)

    def assert_greater_or_equal(self, large_values: typing.Sequence[RelativeDuration], small_values: typing.Sequence[RelativeDuration]):
        if not isinstance(large_values, typing.Sequence):
            large_values = [large_values]

        if not isinstance(small_values, typing.Sequence):
            small_values = [small_values]

        for large_value in large_values:
            for small_value in small_values:
                self.assertGreaterEqual(large_value, small_value)
                self.assertFalse(large_value < small_value)
                self.assertTrue(large_value == small_value or large_value > small_value)

    def assert_greater(self, large_values: typing.Sequence[RelativeDuration], small_values: typing.Sequence[RelativeDuration]):
        if not isinstance(large_values, typing.Sequence):
            large_values = [large_values]

        if not isinstance(small_values, typing.Sequence):
            small_values = [small_values]

        for large_value in large_values:
            for small_value in small_values:
                self.assertGreater(large_value, small_value)
                self.assertFalse(large_value <= small_value)
                self.assertFalse(small_value > large_value)

    def assert_less(self, small_values: typing.Sequence[RelativeDuration], large_values: typing.Sequence[RelativeDuration]):
        if not isinstance(large_values, typing.Sequence):
            large_values = [large_values]

        if not isinstance(small_values, typing.Sequence):
            small_values = [small_values]

        for small_value in small_values:
            for large_value in large_values:
                self.assertLess(small_value, large_value)
                self.assertFalse(small_value >= large_value)
                self.assertFalse(large_value < small_value)

    def assert_less_or_equal(self, small_values: typing.Sequence[RelativeDuration], large_values: typing.Sequence[RelativeDuration]):
        if not isinstance(large_values, typing.Sequence):
            large_values = [large_values]

        if not isinstance(small_values, typing.Sequence):
            small_values = [small_values]

        for small_value in small_values:
            for large_value in large_values:
                self.assertLessEqual(small_value, large_value)
                self.assertFalse(small_value > large_value)
                self.assertTrue(small_value == large_value or small_value < large_value)

    def assert_not_equal(self, same_values: typing.Sequence[RelativeDuration], other_values: typing.Sequence[RelativeDuration]):
        if not isinstance(same_values, typing.Sequence):
            same_values = [same_values]

        if not isinstance(other_values, typing.Sequence):
            other_values = [other_values]

        for same_value in same_values:
            self.assertEqual(same_value, same_value)
            for other_value in other_values:
                self.assertNotEqual(same_value, other_value)


    def test_normalization(self):
        """
        Checks to make sure that the normalization operations produce the same numbers
        """
        self.assertEqual(self.short_normal_duration.dict(), self.short_convoluted_duration.dict())
        self.assertEqual(self.medium_normal_duration.dict(), self.medium_convoluted_duration.dict())
        self.assertEqual(self.long_normal_duration.dict(), self.long_convoluted_duration.dict())

    def test_str(self):
        """
        Checks to make sure that the __str__ function produces the correct ISO 8601 string
        """
        pass

    def test_short_after(self):
        """
        Checks to make sure that the 'after' function works for the short durations
        """
        pass

    def test_medium_after(self):
        """
        Checks to make sure that the 'after' function works for the medium durations
        """
        pass

    def test_long_after(self):
        """
        Checks to make sure that the 'after' function works for the long durations
        """
        pass

    def test_short_prior(self):
        """
        Checks to make sure that the 'prior' function works for the short durations
        """
        pass

    def test_medium_prior(self):
        """
        Checks to make sure that the 'prior' function works for the medium durations
        """
        pass

    def test_long_prior(self):
        """
        Checks to make sure that the 'prior' function works for the long durations
        """
        pass


if __name__ == '__main__':
    unittest.main()
