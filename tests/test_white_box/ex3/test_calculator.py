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


def test_divide_method():
    calc = Calculator()
    result = calc.divide(15.0, 3.0)
    assert result == 5.0
    assert calc.get_last_result() == 5.0


def test_average_empty_list():
    with pytest.raises(ValueError, match="List cannot be empty"):
        average([])


def test_find_min_empty_list():
    with pytest.raises(ValueError, match="List cannot be empty"):
        find_min([])


def test_find_max_empty_list():
    with pytest.raises(ValueError, match="List cannot be empty"):
        find_max([])


def test_power_method():
    calc = Calculator()
    result = calc.power(2.0, 3.0)
    assert result == 8.0
    assert calc.get_last_result() == 8.0


def test_divide_by_zero():
    calc = Calculator()
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        calc.divide(5.0, 0.0)


def test_multiply_method():
    calc = Calculator()
    result = calc.multiply(6.0, 7.0)
    assert result == 42.0
    assert calc.get_last_result() == 42.0


def test_subtract_method():
    calc = Calculator()
    result = calc.subtract(10.0, 4.0)
    assert result == 6.0
    assert calc.get_last_result() == 6.0


def test_add_method():
    calc = Calculator()
    result = calc.add(5.0, 3.0)
    assert result == 8.0
    assert calc.get_last_result() == 8.0
