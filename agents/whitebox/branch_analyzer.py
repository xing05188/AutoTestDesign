"""
branch_analyzer.py
==================
Branch coverage analysis via coverage.py's programmatic API.

Identifies which (from_line → to_line) arcs were never taken during
test execution, then enriches each missing arc with source context
so the LLM has enough information to write a targeted test.

Typical usage
-------------
    analyzer = BranchAnalyzer("mymodule.py")
    analyzer.run_tests_with_coverage(["tests/"])
    missing = analyzer.get_missing_branches()
    summary = analyzer.get_coverage_summary()
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import coverage  # pip install coverage


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MissingBranch:
    """A branch arc that was never taken during the test run."""

    from_line: int          # line where the decision is made
    to_line: int            # line that should have been jumped to
    from_source: str        # the source text of from_line
    context: str            # ±5 lines of numbered source for LLM context
    branch_description: str # human-readable explanation of the gap

    def to_prompt_text(self) -> str:
        """Format for inclusion in an LLM prompt."""
        return (
            f"Missing branch: line {self.from_line} → line {self.to_line}\n"
            f"Description   : {self.branch_description}\n"
            f"Context:\n{self.context}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class BranchAnalyzer:
    """
    Wraps coverage.py to provide branch-level gap analysis.

    Parameters
    ----------
    source_file : str
        Path to the Python module under test.
    coverage_data_file : str
        Path where coverage.py writes its `.coverage` database.
        Defaults to the standard `.coverage` in the working directory.
    """

    def __init__(
        self,
        source_file: str,
        coverage_data_file: str = ".coverage",
    ) -> None:
        self.source_file = Path(source_file).resolve()
        self.coverage_data_file = coverage_data_file
        self._cov: Optional[coverage.Coverage] = None

    # ── public API ────────────────────────────────────────────────────────────

    def run_tests_with_coverage(
        self,
        test_paths: list[str] | None = None,
        extra_pytest_args: list[str] | None = None,
    ) -> dict:
        """
        Execute pytest with branch coverage via pytest-cov, then load the result.

        Returns a summary dict (see `get_coverage_summary`).

        Parameters
        ----------
        test_paths : list of str
            Paths passed directly to pytest (files or directories).
            Defaults to ``["tests"]``.
        extra_pytest_args : list of str
            Any additional arguments forwarded to pytest (e.g. ``["-x"]``).
        """
        test_paths = test_paths or ["tests"]
        extra_pytest_args = extra_pytest_args or []

        # We delegate to pytest-cov via subprocess so that the .coverage file
        # is written by the child process with full instrumentation.
        cmd = [
            sys.executable, "-m", "pytest",
            f"--cov={self.source_file.parent}",
            "--cov-branch",
            "--cov-report=",           # suppress terminal report
            f"--cov-config=",          # use defaults
            *extra_pytest_args,
            *test_paths,
        ]

        coverage_path = Path(self.coverage_data_file)
        if coverage_path.exists():
            coverage_path.unlink()

        subprocess.run(cmd, check=False)   # don't raise on test failures

        if not coverage_path.exists():
            return {
                "branch_coverage_pct": 0.0,
                "covered_branches": 0,
                "total_branches": 0,
                "missing_branches": 0,
                "missing_statements": 0,
                "error": f"Coverage data file not generated: {coverage_path}",
            }

        # Load the coverage data written by pytest-cov
        try:
            self._cov = coverage.Coverage(
                branch=True,
                data_file=self.coverage_data_file,
            )
            self._cov.load()
            return self.get_coverage_summary()
        except Exception as exc:
            return {
                "branch_coverage_pct": 0.0,
                "covered_branches": 0,
                "total_branches": 0,
                "missing_branches": 0,
                "missing_statements": 0,
                "error": str(exc),
            }

    def get_missing_branches(self) -> list[MissingBranch]:
        """
        Return every branch arc that was not taken during the test run.

        Each `MissingBranch` includes source context ready for an LLM prompt.
        """
        self._ensure_loaded()
        source_lines = self.source_file.read_text(encoding="utf-8").splitlines()
        missing: list[MissingBranch] = []

        for from_line, to_line in self._missing_arcs():
            src = (
                source_lines[from_line - 1].rstrip()
                if 0 < from_line <= len(source_lines)
                else ""
            )
            missing.append(
                MissingBranch(
                    from_line=from_line,
                    to_line=to_line,
                    from_source=src,
                    context=self._context_window(source_lines, from_line),
                    branch_description=self._describe_arc(source_lines, from_line, to_line),
                )
            )
        return missing

    def get_coverage_summary(self) -> dict:
        """
        Return a dict with branch coverage statistics.

        Keys: branch_coverage_pct, covered_branches, total_branches,
              missing_branches, missing_statements.
        """
        self._ensure_loaded()
        try:
            analysis = self._cov._analyze(str(self.source_file))
            missing_arcs = self._missing_arcs()

            executed_arcs = self._cov.get_data().arcs(str(self.source_file)) or []
            total = len(executed_arcs) + len(missing_arcs)
            covered = len(executed_arcs)
            pct = round(covered / total * 100, 1) if total else 100.0

            return {
                "branch_coverage_pct": pct,
                "covered_branches": covered,
                "total_branches": total,
                "missing_branches": len(missing_arcs),
                "missing_statements": len(analysis.missing),
            }
        except Exception as exc:
            return {"error": str(exc)}

    # ── private helpers ───────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._cov is None:
            self._cov = coverage.Coverage(branch=True, data_file=self.coverage_data_file)
            self._cov.load()

    def _missing_arcs(self) -> list[tuple[int, int]]:
        """Use coverage.py internals to get (from, to) arcs not yet taken."""
        analysis = self._cov._analyze(str(self.source_file))
        pairs: list[tuple[int, int]] = []
        for from_line, to_lines in analysis.missing_branch_arcs().items():
            for to_line in to_lines:
                pairs.append((from_line, to_line))
        return pairs

    @staticmethod
    def _context_window(lines: list[str], center: int, window: int = 5) -> str:
        start = max(0, center - window - 1)
        end = min(len(lines), center + window)
        return "\n".join(f"{i + 1:4d}: {lines[i]}" for i in range(start, end))

    @staticmethod
    def _describe_arc(lines: list[str], from_line: int, to_line: int) -> str:
        src = lines[from_line - 1].strip() if 0 < from_line <= len(lines) else ""

        # coverage.py uses negative numbers to represent exception/exit paths
        if to_line < 0:
            return (
                f"Line {from_line} ({src!r}): "
                f"exception / early-exit path not covered"
            )

        # Back-edge: loop body never iterated more than once (or loop never entered)
        if to_line <= from_line:
            return (
                f"Line {from_line} ({src!r}): "
                f"loop back-edge to line {to_line} not taken "
                f"(loop body may never have repeated)"
            )

        stripped = src.lstrip()

        if stripped.startswith(("if ", "elif ")):
            # Small gap → next statement → TRUE branch wasn't taken
            # Large gap → skip block → FALSE / else branch wasn't taken
            if to_line == from_line + 1:
                return f"Line {from_line} ({src!r}): TRUE branch not covered"
            return (
                f"Line {from_line} ({src!r}): "
                f"FALSE branch (fall-through / else → line {to_line}) not covered"
            )

        if stripped.startswith("while "):
            return (
                f"Line {from_line} ({src!r}): "
                f"while-loop FALSE branch (loop never entered) not covered"
            )

        if stripped.startswith("for "):
            return (
                f"Line {from_line} ({src!r}): "
                f"for-loop empty-iterable branch not covered"
            )

        if stripped.startswith("try"):
            return f"Line {from_line} ({src!r}): try-block exception path not covered"

        return f"Line {from_line} → line {to_line}: {src!r}"
