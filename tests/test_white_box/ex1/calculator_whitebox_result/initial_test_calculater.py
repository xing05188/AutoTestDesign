import pytest

from calculator import Calculator, find_max, find_min, average


def test_smoke():
    """Smoke test to verify the test file is importable and runnable."""
    assert True


def test_calculator_initialization():
    """Test that Calculator can be instantiated."""
    calc = Calculator()
    assert isinstance(calc, Calculator)
    assert calc.get_last_result() == 0


def test_find_max_non_empty_list():
    """Test find_max with a simple non-empty list."""
    assert find_max([1, 2, 3]) == 3


def test_find_min_non_empty_list():
    """Test find_min with a simple non-empty list."""
    assert find_min([1, 2, 3]) == 1


def test_average_non_empty_list():
    """Test average with a simple non-empty list."""
    assert average([1, 2, 3]) == 2.0
