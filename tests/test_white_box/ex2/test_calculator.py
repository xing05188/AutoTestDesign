import pytest

from calculator import Calculator, find_max, find_min, average


def test_smoke():
    """Smoke test to verify the test file is importable and runnable."""
    assert True


def test_calculator_initialization():
    """Test that Calculator can be instantiated."""
    calc = Calculator()
    assert isinstance(calc, Calculator)


def test_find_max_basic():
    """Basic test for find_max function."""
    assert find_max([1, 2, 3]) == 3


def test_find_min_basic():
    """Basic test for find_min function."""
    assert find_min([1, 2, 3]) == 1


def test_average_basic():
    """Basic test for average function."""
    assert average([1, 2, 3]) == 2.0


def test_find_min_empty_list():
    """Test that find_min raises ValueError when list is empty."""
    with pytest.raises(ValueError, match="List cannot be empty"):
        find_min([])


def test_average_empty_list():
    """Test that average raises ValueError when list is empty."""
    with pytest.raises(ValueError, match="List cannot be empty"):
        average([])


def test_find_max_empty_list():
    """Test that find_max raises ValueError when list is empty."""
    with pytest.raises(ValueError, match="List cannot be empty"):
        find_max([])


def test_divide_by_zero():
    """Test that divide method raises ValueError when divisor is zero."""
    calc = Calculator()
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        calc.divide(5.0, 0.0)


def test_power_method_updates_last_result():
    """Test that the power method correctly computes and stores the exponentiation result."""
    calc = Calculator()
    result = calc.power(2.0, 3.0)
    assert result == 8.0
    assert calc.get_last_result() == 8.0


def test_multiply_method_updates_last_result():
    """Test that the multiply method correctly computes and stores the product."""
    calc = Calculator()
    result = calc.multiply(6.0, 7.0)
    assert result == 42.0
    assert calc.get_last_result() == 42.0


def test_subtract_method_updates_last_result():
    """Test that the subtract method correctly computes and stores the difference."""
    calc = Calculator()
    result = calc.subtract(10.0, 4.0)
    assert result == 6.0
    assert calc.get_last_result() == 6.0


def test_add_method_updates_last_result():
    """Test that the add method correctly computes and stores the sum."""
    calc = Calculator()
    result = calc.add(5.0, 3.0)
    assert result == 8.0
    assert calc.get_last_result() == 8.0
