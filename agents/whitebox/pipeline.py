"""
pipeline.py
===========
Main orchestration: runs the iterative coverage-improvement loop.

Flow per iteration
------------------
1. Run existing tests with branch coverage (pytest-cov).
2. Collect missing branch arcs       → BranchAnalyzer
3. Collect compound conditions        → ConditionAnalyzer (static, once only)
4. Call LLM to generate new tests     → TestGenerator
5. Append generated tests to the test file (with .bak backup).
6. Re-run tests to measure the improvement.
7. Repeat until the target is reached or max_iterations exhausted.

Typical usage
-------------
    from pipeline import CoverageImprovementPipeline

    pipeline = CoverageImprovementPipeline(
        source_file="mymodule.py",
        test_file="tests/test_mymodule.py",
        api_key=os.environ["OPENAI_API_KEY"],
        api_base=os.environ["OPENAI_API_URL"],
        model=os.environ["OPENAI_MODEL"],
    )
    result = pipeline.run(target_branch_coverage=90.0, max_iterations=3)
    print(result)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from branch_analyzer import BranchAnalyzer, MissingBranch
from condition_analyzer import ConditionAnalyzer, CompoundCondition
from test_generator import TestGenerator, GeneratedTests


# ─────────────────────────────────────────────────────────────────────────────
# Result data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IterationResult:
    iteration: int
    branch_coverage_before: float
    branch_coverage_after: float
    missing_branches_before: int
    missing_branches_after: int
    generated_tests: int
    syntax_ok: bool
    new_test_code: str


@dataclass
class PipelineResult:
    source_file: str
    test_file: str
    target_coverage: float
    iterations: list[IterationResult] = field(default_factory=list)
    final_branch_coverage: float = 0.0
    total_tests_added: int = 0
    target_reached: bool = False

    def __str__(self) -> str:
        lines = [
            "═" * 60,
            "Coverage Improvement Pipeline – Final Report",
            "═" * 60,
            f"Source file    : {self.source_file}",
            f"Test file      : {self.test_file}",
            f"Target         : {self.target_coverage:.1f}%",
            f"Final coverage : {self.final_branch_coverage:.1f}%",
            f"Target reached : {'✓' if self.target_reached else '✗'}",
            f"Iterations run : {len(self.iterations)}",
            f"Tests added    : {self.total_tests_added}",
        ]
        for it in self.iterations:
            lines.append(
                f"  Iter {it.iteration}: "
                f"{it.branch_coverage_before:.1f}% → {it.branch_coverage_after:.1f}%  "
                f"(+{it.generated_tests} tests"
                + ("" if it.syntax_ok else ", ⚠ syntax error")
                + ")"
            )
        lines.append("═" * 60)
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class CoverageImprovementPipeline:
    """
    Iterative white-box test generator for branch and condition coverage.

    Parameters
    ----------
    source_file : str
        Python module to test.
    test_file : str
        Existing pytest file to append generated tests to.
    api_key : str
        OpenAI-compatible API key. Defaults to the ``OPENAI_API_KEY`` env var.
    api_base : str
        Base URL for the OpenAI-compatible chat/completions endpoint.
    model : str
        Model identifier.
    include_conditions : bool
        Whether to also generate MC/DC condition tests (default True).
    coverage_data_file : str
        Where coverage.py writes its `.coverage` database.
    """

    def __init__(
        self,
        source_file: str,
        test_file: str,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        include_conditions: bool = True,
        coverage_data_file: str = ".coverage",
    ) -> None:
        self.source_file = Path(source_file).resolve()
        self.test_file = Path(test_file).resolve()
        self.include_conditions = include_conditions

        resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "OpenAI-compatible API key required. Pass api_key= or set OPENAI_API_KEY."
            )

        self._branch_analyzer = BranchAnalyzer(
            str(self.source_file), coverage_data_file
        )
        self._condition_analyzer = ConditionAnalyzer(str(self.source_file))
        self._generator = TestGenerator(
            api_key=resolved_key,
            api_base=api_base or os.environ.get("OPENAI_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            model=model or os.environ.get("OPENAI_MODEL", "qwen-plus"),
        )

    # ── public API ────────────────────────────────────────────────────────────

    def run(
        self,
        target_branch_coverage: float = 85.0,
        max_iterations: int = 3,
        test_paths: list[str] | None = None,
        extra_pytest_args: list[str] | None = None,
    ) -> PipelineResult:
        """
        Run the iterative improvement loop.

        Parameters
        ----------
        target_branch_coverage : float
            Stop early when branch coverage reaches this percentage.
        max_iterations : int
            Hard cap on the number of LLM + test-run cycles.
        test_paths : list of str
            Paths passed to pytest.  Defaults to ``[str(self.test_file)]``.
        extra_pytest_args : list of str
            Extra flags forwarded to pytest (e.g. ``["-x", "--tb=short"]``).

        Returns
        -------
        PipelineResult
            Full history of every iteration plus the final coverage figure.
        """
        test_paths = test_paths or [str(self.test_file)]
        extra_pytest_args = extra_pytest_args or []

        result = PipelineResult(
            source_file=str(self.source_file),
            test_file=str(self.test_file),
            target_coverage=target_branch_coverage,
        )

        source_code = self.source_file.read_text()

        # ── Static analysis: compound conditions (done once) ───────────────
        all_conditions: list[CompoundCondition] = []
        if self.include_conditions:
            all_conditions = self._condition_analyzer.get_compound_conditions()
            _log(
                f"Found {len(all_conditions)} compound condition(s) in "
                f"{self.source_file.name}"
            )

        pending_conditions = list(all_conditions)  # consumed in iteration 1

        # ── Iterative loop ──────────────────────────────────────────────────
        for i in range(1, max_iterations + 1):
            _section(f"Iteration {i} / {max_iterations}")

            # Step 1 – measure current branch coverage
            summary_before = self._branch_analyzer.run_tests_with_coverage(
                test_paths, extra_pytest_args
            )
            cov_before = summary_before.get("branch_coverage_pct", 0.0)
            miss_before = summary_before.get("missing_branches", 0)
            _log(
                f"Branch coverage: {cov_before:.1f}%  "
                f"({miss_before} missing arc(s))"
            )

            if cov_before >= target_branch_coverage and i > 1:
                _log(f"Target {target_branch_coverage:.1f}% reached – stopping early.")
                result.target_reached = True
                break

            # Step 2 – collect coverage gaps
            missing_branches = self._branch_analyzer.get_missing_branches()
            conditions_this_iter = pending_conditions  # only inject in first iteration

            if not missing_branches and not conditions_this_iter:
                _log("No coverage gaps found – nothing to do.")
                result.target_reached = cov_before >= target_branch_coverage
                break

            _print_gaps(missing_branches, conditions_this_iter)

            # Step 3 – generate new tests via LLM
            existing_tests = self.test_file.read_text()
            generated: GeneratedTests = self._generator.generate_combined(
                source_code=source_code,
                existing_tests=existing_tests,
                missing_branches=missing_branches,
                conditions=conditions_this_iter,
                module_name=self.source_file.stem,
            )
            _log(
                f"LLM generated {generated.num_tests} test(s)"
                + ("" if generated.syntax_ok else "  ⚠ syntax error detected")
            )

            if not generated.test_code.strip():
                _log("LLM returned empty output – stopping.")
                break

            # Step 4 – append to test file (backup first)
            self._append_tests(generated.test_code, iteration=i)
            pending_conditions = []  # don't re-inject condition prompts

            # Step 5 – re-measure
            summary_after = self._branch_analyzer.run_tests_with_coverage(
                test_paths, extra_pytest_args
            )
            cov_after = summary_after.get("branch_coverage_pct", 0.0)
            miss_after = summary_after.get("missing_branches", 0)
            _log(
                f"Branch coverage after: {cov_after:.1f}%  "
                f"({miss_after} missing arc(s))"
            )

            result.iterations.append(
                IterationResult(
                    iteration=i,
                    branch_coverage_before=cov_before,
                    branch_coverage_after=cov_after,
                    missing_branches_before=miss_before,
                    missing_branches_after=miss_after,
                    generated_tests=generated.num_tests,
                    syntax_ok=generated.syntax_ok,
                    new_test_code=generated.test_code,
                )
            )
            result.total_tests_added += generated.num_tests

        # ── Final measurement ───────────────────────────────────────────────
        final = self._branch_analyzer.run_tests_with_coverage(
            test_paths, extra_pytest_args
        )
        result.final_branch_coverage = final.get("branch_coverage_pct", 0.0)
        result.target_reached = result.final_branch_coverage >= target_branch_coverage

        print(result)
        return result

    # ── helpers ───────────────────────────────────────────────────────────────

    def _append_tests(self, code: str, iteration: int) -> None:
        """Append the generated tests to the test file."""
        separator = (
            f"\n\n# {'-' * 56}\n"
            f"# Auto-generated - iteration {iteration} "
            f"(CoverageImprovementPipeline)\n"
            f"# {'-' * 56}\n\n"
        )
        with self.test_file.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(separator + code + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Logging helpers
# ─────────────────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"[Pipeline] {msg}")


def _section(title: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"[Pipeline] {title}")
    print(f"{'═' * 60}")


def _print_gaps(
    branches: list[MissingBranch],
    conditions: list[CompoundCondition],
) -> None:
    if branches:
        _log(f"Missing branches ({len(branches)}):")
        for b in branches[:6]:
            print(f"    • {b.branch_description}")
        if len(branches) > 6:
            print(f"    … and {len(branches) - 6} more")

    if conditions:
        _log(f"Compound conditions to cover ({len(conditions)}):")
        for c in conditions[:6]:
            print(
                f"    • line {c.line}: `{c.full_expression}` "
                f"→ {len(c.mcdc_cases)} MC/DC case(s)"
            )
        if len(conditions) > 6:
            print(f"    … and {len(conditions) - 6} more")
