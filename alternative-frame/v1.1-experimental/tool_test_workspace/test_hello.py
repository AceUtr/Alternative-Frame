import unittest

from hello import add


class TestAdd(unittest.TestCase):
    def test_add_two_integers(self):
        self.assertEqual(add(2, 3), 5)


if __name__ == "__main__":
    unittest.main()
