"""
A simple calculator module for basic arithmetic operations.
"""

class Calculator:
    """A simple calculator that performs basic arithmetic operations."""
    
    def __init__(self):
        """Initialize the calculator."""
        self.last_result = 0
    
    def add(self, a: float, b: float) -> float:
        """
        Add two numbers.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Sum of a and b
        """
        self.last_result = a + b
        return self.last_result
    
    def subtract(self, a: float, b: float) -> float:
        """
        Subtract b from a.
        
        Args:
            a: First number
            b: Second number to subtract
            
        Returns:
            Difference of a and b
        """
        self.last_result = a - b
        return self.last_result
    
    def multiply(self, a: float, b: float) -> float:
        """
        Multiply two numbers.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Product of a and b
        """
        self.last_result = a * b
        return self.last_result
    
    def divide(self, a: float, b: float) -> float:
        """
        Divide a by b.
        
        Args:
            a: Dividend
            b: Divisor
            
        Returns:
            Result of a divided by b
            
        Raises:
            ValueError: If b is zero
        """
        if b == 0:
            raise ValueError("Cannot divide by zero")
        self.last_result = a / b
        return self.last_result
    
    def power(self, base: float, exponent: float) -> float:
        """
        Raise base to the power of exponent.
        
        Args:
            base: The base number
            exponent: The exponent
            
        Returns:
            base raised to the power of exponent
        """
        self.last_result = base ** exponent
        return self.last_result
    
    def get_last_result(self) -> float:
        """
        Get the last calculated result.
        
        Returns:
            The last result
        """
        return self.last_result


def find_max(numbers: list) -> float:
    """
    Find the maximum number in a list.
    
    Args:
        numbers: List of numbers
        
    Returns:
        The maximum number
        
    Raises:
        ValueError: If the list is empty
    """
    if not numbers:
        raise ValueError("List cannot be empty")
    return max(numbers)


def find_min(numbers: list) -> float:
    """
    Find the minimum number in a list.
    
    Args:
        numbers: List of numbers
        
    Returns:
        The minimum number
        
    Raises:
        ValueError: If the list is empty
    """
    if not numbers:
        raise ValueError("List cannot be empty")
    return min(numbers)


def average(numbers: list) -> float:
    """
    Calculate the average of a list of numbers.
    
    Args:
        numbers: List of numbers
        
    Returns:
        The average of the numbers
        
    Raises:
        ValueError: If the list is empty
    """
    if not numbers:
        raise ValueError("List cannot be empty")
    return sum(numbers) / len(numbers)
