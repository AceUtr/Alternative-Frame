"""Small deterministic word-counting fixture used by retry demonstrations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class WordCountError(ValueError):
    """Base error for invalid word-count inputs."""


class TextInputError(WordCountError):
    pass


class TextFileError(WordCountError):
    pass


@dataclass(frozen=True)
class WordCountResult:
    words: int
    characters: int
    lines: int


def count_words(text: str) -> int:
    if not isinstance(text, str):
        raise TextInputError("text must be a string")
    return len(text.split())


def count_text(text: str) -> WordCountResult:
    if not isinstance(text, str):
        raise TextInputError("text must be a string")
    return WordCountResult(
        words=count_words(text),
        characters=len(text),
        lines=0 if text == "" else len(text.splitlines()),
    )


def count_file(path: str | Path) -> WordCountResult:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise TextFileError(f"unable to read text file: {path}") from exc
    return count_text(text)
