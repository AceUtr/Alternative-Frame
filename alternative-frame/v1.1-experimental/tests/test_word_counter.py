import tempfile
import unittest
from pathlib import Path

from retry_demo.word_counter import (
    TextFileError,
    TextInputError,
    WordCountResult,
    count_file,
    count_text,
    count_words,
)


class WordCounterTests(unittest.TestCase):
    def test_count_words_handles_whitespace_and_unicode(self) -> None:
        self.assertEqual(count_words("  hello\tworld\n你好  "), 3)

    def test_count_text_returns_all_counts(self) -> None:
        self.assertEqual(
            count_text("one two\nthree"),
            WordCountResult(words=3, characters=13, lines=2),
        )
        self.assertEqual(count_text(""), WordCountResult(0, 0, 0))

    def test_count_text_rejects_non_string_input(self) -> None:
        with self.assertRaises(TextInputError):
            count_text(None)  # type: ignore[arg-type]

    def test_count_file_reads_utf8_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.write_text("alpha beta\ngamma", encoding="utf-8")

            self.assertEqual(count_file(path), WordCountResult(3, 16, 2))

    def test_count_file_wraps_read_errors(self) -> None:
        with self.assertRaises(TextFileError):
            count_file("missing-word-counter-input.txt")


if __name__ == "__main__":
    unittest.main()
