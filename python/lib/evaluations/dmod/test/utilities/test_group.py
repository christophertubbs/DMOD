import unittest

from ...evaluations.utilities import group


class GroupTest(unittest.TestCase):
    identity_set: group.FiniteGroup[str] = group.FiniteGroup("Identity", ["A"])
    confusing_set: group.FiniteGroup[int] = group.FiniteGroup(
        "Confusing Set",
        [
            5,   # 0,  7, 14, 21, 28, -1,  -8
            4,   # 1,  8, 15, 22, 29, -2,  -9
            3,   # 2,  9, 16, 23, 30, -3, -10
            8,   # 3, 10, 17, 24, 31, -4, -11
            9,   # 4, 11, 18, 25, 32, -5, -12
            10,  # 5, 12, 19, 26, 33, -6, -13
            1    # 6, 13, 20, 27, 34, -7, -14
        ]
    )

    def test_comparisons(self):
        identity = self.identity_set("A")
        confusing_value = self.confusing_set(10)

        self.assertGreater("B", identity)

        self.assertEqual(identity, "A")
        self.assertEqual(self.identity_set("A"), self.identity_set("A"))

        self.assertGreater(confusing_value, 3)
        self.assertGreater(confusing_value.value, 3)
        self.assertLess(confusing_value, 12)
        self.assertLess(confusing_value.value, 12)
        self.assertLess(self.confusing_set(8), self.confusing_set(1))

    def test_creation(self):
        self.assertEqual(self.identity_set("A"), "A")
        self.assertEqual(self.identity_set("A"), self.identity_set.by_index(0))

        self.assertEqual(self.confusing_set(3), self.confusing_set[3])
        self.assertEqual(self.confusing_set.by_index(2), self.confusing_set.get(3))

    def test_operations(self):
        identity = self.identity_set.get(0)
        self.assertEqual(identity, "A")
        added_identity = identity + 12
        self.assertEqual(added_identity, "A")
        subtracted_identity = identity - 1
        self.assertEqual(subtracted_identity, "A")

        confusing_value = self.confusing_set.by_index(29)
        self.assertEqual(confusing_value, 4)
        confusing_value.increment()
        self.assertEqual(confusing_value, 3)
        confusing_value.decrement(2)
        self.assertEqual(confusing_value, 5)
        confusing_value += 4
        self.assertEqual(confusing_value, 4)
        confusing_value += 3
        self.assertEqual(confusing_value, 8)
        confusing_value.decrement(3)
        self.assertEqual(confusing_value, 5)
        confusing_value -= 2
        self.assertEqual(confusing_value, 10)


if __name__ == '__main__':
    unittest.main()
