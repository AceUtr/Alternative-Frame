"""Tests for the public calculator API."""

import pytest

from calculator import add


def test_add_positive_numbers() -> None:
    assert add(2, 3) == 5


def test_add_negative_numbers() -> None:
    assert add(-2, -3) == -5


def test_add_zero() -> None:
    assert add(0, 7) == 7
    assert add(0, 0) == 0


def test_add_floating_point_numbers() -> None:
    assert add(0.1, 0.2) == pytest.approx(0.3)
