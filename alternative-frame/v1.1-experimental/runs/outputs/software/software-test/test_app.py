from app import add


def test_add():
    assert add(1, 2) == 3
    assert add(-2, 5) == 3
