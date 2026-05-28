"""
condition_analyzer.py
=====================
Condition / MC-DC coverage analysis using Python's built-in ``ast`` module.

What it does
------------
1. Parses the source file into an AST and walks every BoolOp node
   (``and`` / ``or`` expressions).
2. For each compound condition it computes the **minimal MC/DC test matrix**:
   each sub-condition must independently affect the overall result.
3. Optionally calls **CrossHair** (symbolic execution) to generate *concrete*
   input values for pure / side-effect-free functions.

Why AST instead of a coverage tool?
------------------------------------
Standard coverage.py only tracks branch arcs (taken / not taken), not the
truth value of individual sub-conditions inside a compound expression.
There is no mainstream Python tool that tracks condition coverage directly,
so we derive it statically from the AST and ask the LLM to write tests that
satisfy each MC/DC case.

Typical usage
-------------
    analyzer = ConditionAnalyzer("mymodule.py")
    conditions = analyzer.get_compound_conditions()
    for c in conditions:
        print(c.to_prompt_text())

    # Optional: CrossHair for pure functions
    inputs = analyzer.get_crosshair_inputs("my_pure_function")
"""
from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MCDCCase:
    """
    One row in the MC/DC test matrix.

    Describes the combination of sub-condition truth values that demonstrates
    one sub-condition independently affecting the overall boolean result.
    """
    description: str
    sub_condition_values: dict[str, bool]  # {expression_str: True | False}
    expected_overall: bool

    def to_prompt_text(self) -> str:
        vals = ", ".join(
            f"`{k}` = {v}" for k, v in self.sub_condition_values.items()
        )
        return (
            f"  {self.description}\n"
            f"  Values  : {vals}\n"
            f"  Expected: {self.expected_overall}"
        )


@dataclass
class CompoundCondition:
    """
    A BoolOp node (``and`` / ``or``) found in the source code, together
    with the MC/DC cases needed to exercise every sub-condition independently.
    """
    line: int
    col_offset: int
    operator: str               # "and" | "or"
    full_expression: str        # e.g. "x > 0 and y > 0"
    sub_conditions: list[str]   # ["x > 0", "y > 0"]
    context: str                # numbered source lines around this node
    enclosing_function: str     # name of the containing function (if any)
    mcdc_cases: list[MCDCCase] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        cases_text = "\n".join(c.to_prompt_text() for c in self.mcdc_cases)
        return (
            f"Compound condition on line {self.line}: `{self.full_expression}`\n"
            f"Operator        : {self.operator}\n"
            f"Sub-conditions  : {self.sub_conditions}\n"
            f"Function        : {self.enclosing_function or '(module level)'}\n"
            f"MC/DC cases required:\n{cases_text}\n"
            f"Context:\n{self.context}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class ConditionAnalyzer:
    """
    Statically analyse a Python source file for compound boolean conditions
    and generate MC/DC test requirements for each one.

    Parameters
    ----------
    source_file : str
        Path to the Python module under test.
    """

    def __init__(self, source_file: str) -> None:
        self.source_file = Path(source_file).resolve()
        self._source = self.source_file.read_text(encoding="utf-8")
        self._lines = self._source.splitlines()
        self._tree = ast.parse(self._source, filename=str(self.source_file))

    # ── public API ────────────────────────────────────────────────────────────

    def get_compound_conditions(self) -> list[CompoundCondition]:
        """
        Return every compound boolean condition in the source, each annotated
        with its MC/DC test matrix.

        Nested BoolOps are reported individually (e.g. ``(A and B) or C``
        yields two entries: one for the inner ``and``, one for the outer ``or``).
        """
        visitor = _BoolOpVisitor(self._lines)
        visitor.visit(self._tree)
        return visitor.conditions

    def get_crosshair_inputs(
        self,
        function_name: str,
        timeout: int = 15,
    ) -> list[dict[str, str]]:
        """
        Run ``crosshair cover`` on *function_name* in this module and parse
        the generated inputs.

        Returns a (possibly empty) list of argument dicts.
        Fails gracefully if CrossHair is not installed or the function has
        side-effects that prevent symbolic execution.

        Parameters
        ----------
        function_name : str
            The unqualified name of the function to analyse.
        timeout : int
            Maximum seconds to wait for CrossHair.
        """
        module = self.source_file.stem
        target = f"{module}.{function_name}"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "crosshair", "cover", target],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.source_file.parent,
            )
            parsed = _parse_crosshair_output(result.stdout)
            if parsed:
                print(
                    f"[ConditionAnalyzer] CrossHair generated "
                    f"{len(parsed)} input(s) for {function_name}"
                )
            return parsed

        except FileNotFoundError:
            print(
                "[ConditionAnalyzer] CrossHair not installed – "
                "skipping symbolic execution. "
                "Install with: pip install crosshair-tool"
            )
            return []

        except subprocess.TimeoutExpired:
            print(
                f"[ConditionAnalyzer] CrossHair timed out for {function_name} "
                f"after {timeout}s – skipping."
            )
            return []

        except Exception as exc:
            print(f"[ConditionAnalyzer] CrossHair error: {exc}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# AST visitor
# ─────────────────────────────────────────────────────────────────────────────

class _BoolOpVisitor(ast.NodeVisitor):
    """Walk the AST and collect every BoolOp node with its MC/DC matrix."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.conditions: list[CompoundCondition] = []
        self._function_stack: list[str] = []

    # Track the current enclosing function
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_stack.append(node.name)
        self.generic_visit(node)
        self._function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        op = "and" if isinstance(node.op, ast.And) else "or"
        sub_conditions = [ast.unparse(v) for v in node.values]
        full_expr = ast.unparse(node)

        self.conditions.append(
            CompoundCondition(
                line=node.lineno,
                col_offset=node.col_offset,
                operator=op,
                full_expression=full_expr,
                sub_conditions=sub_conditions,
                context=self._context_window(node.lineno),
                enclosing_function=(
                    self._function_stack[-1] if self._function_stack else ""
                ),
                mcdc_cases=_generate_mcdc_cases(op, sub_conditions),
            )
        )
        # Continue walking so nested BoolOps are also captured
        self.generic_visit(node)

    def _context_window(self, center: int, window: int = 4) -> str:
        start = max(0, center - window - 1)
        end = min(len(self._lines), center + window)
        return "\n".join(
            f"{i + 1:4d}: {self._lines[i]}" for i in range(start, end)
        )


# ─────────────────────────────────────────────────────────────────────────────
# MC/DC case generator
# ─────────────────────────────────────────────────────────────────────────────

def _generate_mcdc_cases(
    op: str, sub_conditions: list[str]
) -> list[MCDCCase]:
    """
    Build the minimal MC/DC test matrix for an ``and`` or ``or`` expression.

    Strategy
    --------
    **AND**  – baseline: all True (result=True).
               For each sub-condition flip it to False; all others stay True.
               This shows it independently causes the result to become False.

    **OR**   – baseline: all False (result=False).
               For each sub-condition flip it to True; all others stay False.
               This shows it independently causes the result to become True.

    The number of cases is N+1 for an N-term expression.
    """
    cases: list[MCDCCase] = []

    if op == "and":
        # Baseline: everything True
        cases.append(
            MCDCCase(
                description="All sub-conditions True → whole expression True",
                sub_condition_values={c: True for c in sub_conditions},
                expected_overall=True,
            )
        )
        # Flip each sub-condition independently to False
        for target in sub_conditions:
            values = {c: True for c in sub_conditions}
            values[target] = False
            cases.append(
                MCDCCase(
                    description=(
                        f"`{target}` is False → whole expression False "
                        f"(independent effect shown)"
                    ),
                    sub_condition_values=values,
                    expected_overall=False,
                )
            )

    else:  # "or"
        # Baseline: everything False
        cases.append(
            MCDCCase(
                description="All sub-conditions False → whole expression False",
                sub_condition_values={c: False for c in sub_conditions},
                expected_overall=False,
            )
        )
        # Flip each sub-condition independently to True
        for target in sub_conditions:
            values = {c: False for c in sub_conditions}
            values[target] = True
            cases.append(
                MCDCCase(
                    description=(
                        f"`{target}` is True → whole expression True "
                        f"(independent effect shown)"
                    ),
                    sub_condition_values=values,
                    expected_overall=True,
                )
            )

    return cases


# ─────────────────────────────────────────────────────────────────────────────
# CrossHair output parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_crosshair_output(output: str) -> list[dict[str, str]]:
    """
    Parse CrossHair ``cover`` output into a list of argument dicts.

    CrossHair lines look like::

        divide(a=1, b=0) -> raises ZeroDivisionError
        divide(a=0, b=1) -> 0.0

    Returns a list of ``{"a": "1", "b": "0"}`` style dicts.
    """
    inputs: list[dict[str, str]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "ERROR", "WARNING")):
            continue
        try:
            paren_open = line.index("(")
            paren_close = line.rindex(")")
            args_str = line[paren_open + 1 : paren_close]
            args: dict[str, str] = {}
            for part in args_str.split(","):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    args[k.strip()] = v.strip()
            if args:
                inputs.append(args)
        except (ValueError, IndexError):
            continue
    return inputs
