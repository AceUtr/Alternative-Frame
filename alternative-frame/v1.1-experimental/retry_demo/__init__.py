"""Small, dependency-free examples used by retry demonstrations."""

from .word_counter import (
    TextFileError,
    TextInputError,
    WordCountError,
    WordCountResult,
    count_file,
    count_text,
    count_words,
)

__all__ = [
    "TextFileError",
    "TextInputError",
    "WordCountError",
    "WordCountResult",
    "count_file",
    "count_text",
    "count_words",
]
