import pytest

from app import add


def test_add_positive_numbers():
    assert add(1, 2) == 3


def test_add_negative_numbers():
    assert add(-4, -6) == -10


def test_add_zero():
    assert add(5, 0) == 5


def test_add_float_numbers():
    assert add(0.1, 0.2) == pytest.approx(0.3)

