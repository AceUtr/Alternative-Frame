"""Tests for retry_demo/word_counter.py."""

import unittest

from word_counter import count_text


class CountTextTests(unittest.TestCase):
    def assert_counts(self, text, expected):
        result = count_text(text)
        self.assertEqual(result, expected)
        self.assertEqual(set(result), {"lines", "words", "characters"})
        for value in result.values():
            self.assertIs(type(value), int)

    def test_empty_string(self):
        self.assert_counts("", {"lines": 0, "words": 0, "characters": 0})

    def test_single_line_english(self):
        text = "Hello world"
        self.assert_counts(text, {"lines": 1, "words": 2, "characters": 11})

    def test_multiline_text(self):
        text = "first line\nsecond line\nthird"
        self.assert_counts(text, {"lines": 3, "words": 5, "characters": 28})

    def test_mixed_chinese_and_english(self):
        text = "你好 world\nPython 测试"
        self.assert_counts(text, {"lines": 2, "words": 4, "characters": 18})


if __name__ == "__main__":
    unittest.main()
