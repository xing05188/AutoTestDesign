"""
example_usage.py
================
Self-contained demo of every component in the white-box coverage toolkit.

Run
---
    ANTHROPIC_API_KEY=sk-ant-... python example_usage.py

The example creates a tiny target module and an initial test file, then
runs the full pipeline.  Afterwards it also shows how to call each
component individually for finer-grained control.
"""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
from pathlib import Path

# ── make sure the package is importable ─────────────────────────────────────
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from branch_analyzer import BranchAnalyzer
from condition_analyzer import ConditionAnalyzer
from test_generator import TestGenerator
from pipeline import CoverageImprovementPipeline


# ─────────────────────────────────────────────────────────────────────────────
# Tiny target module used in the demo
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_SOURCE = textwrap.dedent("""\
    \"\"\"Sample module with several branch and condition coverage gaps.\"\"\"

    def classify_score(score: int, bonus: bool = False) -> str:
        \"\"\"Return a grade label based on a numeric score.\"\"\"
        if score < 0 or score > 100:       # compound OR condition
            raise ValueError(f"Score out of range: {score}")

        if bonus:
            score = min(score + 10, 100)

        if score >= 90 and not bonus:      # compound AND condition
            return "A (no bonus)"
        elif score >= 90:
            return "A"
        elif score >= 70:
            return "B"
        elif score >= 50:
            return "C"
        else:
            return "F"


    def safe_divide(a: float, b: float) -> float:
        \"\"\"Divide a by b, returning 0.0 when b is zero.\"\"\"
        if b == 0:
            return 0.0
        return a / b
""")

# Intentionally thin initial test suite – many branches uncovered
SAMPLE_INITIAL_TESTS = textwrap.dedent("""\
    import pytest
    from sample import classify_score, safe_divide


    def test_classify_score_b():
        \"\"\"Happy-path B grade.\"\"\"
        assert classify_score(75) == "B"


    def test_safe_divide_normal():
        \"\"\"Normal division.\"\"\"
        assert safe_divide(10, 2) == 5.0
""")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: write temporary files
# ─────────────────────────────────────────────────────────────────────────────

def _setup_temp_project(tmp: Path) -> tuple[Path, Path]:
    """Write the sample module and initial tests, return their paths."""
    source = tmp / "sample.py"
    tests_dir = tmp / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_sample.py"

    source.write_text(SAMPLE_SOURCE)
    test_file.write_text(SAMPLE_INITIAL_TESTS)
    return source, test_file


# ─────────────────────────────────────────────────────────────────────────────
# Demo 1 – standalone branch analysis (no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def demo_branch_analysis(source: Path, test_file: Path) -> None:
    print("\n" + "═" * 60)
    print("Demo 1 – Branch Analysis (no LLM)")
    print("═" * 60)

    analyzer = BranchAnalyzer(str(source))
    summary = analyzer.run_tests_with_coverage([str(test_file)])
    print(f"Coverage summary: {summary}")

    missing = analyzer.get_missing_branches()
    print(f"\n{len(missing)} missing branch arc(s):")
    for b in missing:
        print(f"  • {b.branch_description}")
        print(f"    Context preview: {b.from_source!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Demo 2 – standalone condition analysis (no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def demo_condition_analysis(source: Path) -> None:
    print("\n" + "═" * 60)
    print("Demo 2 – Condition / MC-DC Analysis (no LLM)")
    print("═" * 60)

    analyzer = ConditionAnalyzer(str(source))
    conditions = analyzer.get_compound_conditions()

    print(f"\n{len(conditions)} compound condition(s) found:\n")
    for c in conditions:
        print(c.to_prompt_text())
        print()

    # Optional CrossHair call (skip gracefully if not installed)
    print("Attempting CrossHair symbolic execution for safe_divide …")
    inputs = analyzer.get_crosshair_inputs("safe_divide", timeout=10)
    if inputs:
        print(f"CrossHair produced {len(inputs)} input set(s):")
        for args in inputs:
            print(f"  {args}")
    else:
        print("  (CrossHair not available or returned no results)")


# ─────────────────────────────────────────────────────────────────────────────
# Demo 3 – single LLM call for branch tests only
# ─────────────────────────────────────────────────────────────────────────────

def demo_branch_generation(
    source: Path,
    test_file: Path,
    api_key: str,
) -> None:
    print("\n" + "═" * 60)
    print("Demo 3 – LLM: branch test generation")
    print("═" * 60)

    branch_analyzer = BranchAnalyzer(str(source))
    branch_analyzer.run_tests_with_coverage([str(test_file)])
    missing = branch_analyzer.get_missing_branches()

    gen = TestGenerator(api_key=api_key)
    result = gen.generate_for_branches(
        source_code=source.read_text(),
        existing_tests=test_file.read_text(),
        missing_branches=missing,
        module_name="sample",
    )

    print(f"\nGenerated {result.num_tests} test(s). Syntax OK: {result.syntax_ok}")
    print("\nGenerated code:\n" + "─" * 40)
    print(result.test_code)


# ─────────────────────────────────────────────────────────────────────────────
# Demo 4 – full pipeline (branches + conditions, iterative)
# ─────────────────────────────────────────────────────────────────────────────

def demo_full_pipeline(
    source: Path,
    test_file: Path,
    api_key: str,
) -> None:
    print("\n" + "═" * 60)
    print("Demo 4 – Full Pipeline (branch + condition, iterative)")
    print("═" * 60)

    pipeline = CoverageImprovementPipeline(
        source_file=str(source),
        test_file=str(test_file),
        api_key=api_key,
        include_conditions=True,         # also generate MC/DC tests
    )

    result = pipeline.run(
        target_branch_coverage=90.0,     # stop when ≥ 90 % branch coverage
        max_iterations=3,
        test_paths=[str(test_file)],
    )

    print("\nFinal test file contents:")
    print("─" * 40)
    print(test_file.read_text())


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        source, test_file = _setup_temp_project(tmp)

        # Change into the tmp dir so pytest-cov and .coverage are written there
        os.chdir(tmp)

        # Always run the no-LLM demos
        demo_branch_analysis(source, test_file)
        demo_condition_analysis(source)

        # LLM demos require a key
        if not api_key:
            print(
                "\n[example] Set ANTHROPIC_API_KEY to run the LLM demos (Demo 3 & 4)."
            )
            return

        demo_branch_generation(source, test_file, api_key)

        # Reset test file for the pipeline demo
        test_file.write_text(SAMPLE_INITIAL_TESTS)
        demo_full_pipeline(source, test_file, api_key)


if __name__ == "__main__":
    main()
