"""
test_generator.py
=================
LLM-powered pytest test generator using an OpenAI-compatible chat/completions API.

Takes the output of BranchAnalyzer and ConditionAnalyzer and produces
syntactically valid pytest test functions that target the identified gaps.

Typical usage
-------------
    gen = TestGenerator(
        api_key=os.environ["OPENAI_API_KEY"],
        api_base=os.environ["OPENAI_API_URL"],
        model=os.environ["OPENAI_MODEL"],
    )
    result = gen.generate_combined(
        source_code=Path("mymodule.py").read_text(),
        existing_tests=Path("tests/test_mymodule.py").read_text(),
        missing_branches=branch_analyzer.get_missing_branches(),
        conditions=condition_analyzer.get_compound_conditions(),
        module_name="mymodule",
    )
    print(result.test_code)   # valid Python, ready to append
    print(result.num_tests)   # how many test_ functions were generated
"""
from __future__ import annotations

import ast
import os
import textwrap
from dataclasses import dataclass, field

import requests

from branch_analyzer import MissingBranch
from condition_analyzer import CompoundCondition


# ─────────────────────────────────────────────────────────────────────────────
# Return type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GeneratedTests:
    """Result returned by every generate_* method."""
    test_code: str                          # validated Python source
    num_tests: int                          # number of test_ functions found
    coverage_targets: list[str] = field(default_factory=list)  # what was targeted
    syntax_ok: bool = True                  # False if LLM output had a syntax error


# ─────────────────────────────────────────────────────────────────────────────
# Generator
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerator:
    """
    Calls an OpenAI-compatible chat model to produce pytest tests for branch and condition coverage gaps.

    Parameters
    ----------
    api_key : str
        OpenAI-compatible API key (``OPENAI_API_KEY``).
    api_base : str
        Base URL of the OpenAI-compatible chat/completions endpoint provider.
    model : str
        Model identifier to use.
    max_tokens : int
        Maximum tokens in the LLM response.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("OpenAI-compatible API key required. Pass api_key= or set OPENAI_API_KEY.")

        self.api_base = (api_base or os.environ.get("OPENAI_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")).rstrip("/")
        self.model = model or os.environ.get("OPENAI_MODEL", "qwen-plus")
        self.max_tokens = max_tokens

    # ── public API ────────────────────────────────────────────────────────────

    def generate_for_branches(
        self,
        source_code: str,
        existing_tests: str,
        missing_branches: list[MissingBranch],
        module_name: str = "module_under_test",
    ) -> GeneratedTests:
        """Generate tests that cover every missing branch arc."""
        if not missing_branches:
            return GeneratedTests("", 0)

        prompt = self._branch_prompt(
            source_code, existing_tests, missing_branches, module_name
        )
        return self._call_llm(
            prompt,
            targets=[b.branch_description for b in missing_branches],
        )

    def generate_for_conditions(
        self,
        source_code: str,
        existing_tests: str,
        conditions: list[CompoundCondition],
        module_name: str = "module_under_test",
    ) -> GeneratedTests:
        """Generate tests that achieve MC/DC coverage for every compound condition."""
        if not conditions:
            return GeneratedTests("", 0)

        prompt = self._condition_prompt(
            source_code, existing_tests, conditions, module_name
        )
        return self._call_llm(
            prompt,
            targets=[c.full_expression for c in conditions],
        )

    def generate_combined(
        self,
        source_code: str,
        existing_tests: str,
        missing_branches: list[MissingBranch],
        conditions: list[CompoundCondition],
        module_name: str = "module_under_test",
    ) -> GeneratedTests:
        """
        Single LLM call covering both branch and condition gaps.

        Preferred over calling generate_for_branches + generate_for_conditions
        separately because the model can avoid writing redundant tests.
        """
        if not missing_branches and not conditions:
            return GeneratedTests("", 0)

        prompt = self._combined_prompt(
            source_code, existing_tests, missing_branches, conditions, module_name
        )
        targets = (
            [b.branch_description for b in missing_branches]
            + [c.full_expression for c in conditions]
        )
        return self._call_llm(prompt, targets=targets)

    # ── prompt builders ───────────────────────────────────────────────────────

    _RULES = textwrap.dedent("""
        Rules (follow every one):
        1. Every test function name must start with `test_`.
        2. Use `pytest.raises(ExcType)` for exception / error paths.
        3. Use `unittest.mock.patch` or `MagicMock` when the function touches
           I/O, databases, or external services.
          4. Keep tests concise. Avoid comments and docstrings unless strictly necessary.
          5. Use ASCII-only punctuation and text in the generated code.
          6. Do NOT repeat any test already present in the existing suite.
          7. Assume `from {module} import *` is already at the top of the file;
           do not duplicate it.
          8. Output ONLY valid Python source - no markdown fences, no prose.
    """).strip()

    def _branch_prompt(
        self,
        source_code: str,
        existing_tests: str,
        missing_branches: list[MissingBranch],
        module_name: str,
    ) -> str:
        branches_text = "\n\n".join(b.to_prompt_text() for b in missing_branches)
        rules = self._RULES.format(module=module_name)
        return textwrap.dedent(f"""
            You are an expert Python test engineer specialising in white-box testing.

            ## Source code under test
            ```python
            {source_code}
            ```

            ## Existing test suite (DO NOT repeat these tests)
            ```python
            {existing_tests}
            ```

            ## Uncovered branches  (from coverage.py --branch analysis)
            {branches_text}

            ## Task
            Write new pytest test functions that cover every uncovered branch above.
            One or more tests per branch is fine; prefer the fewest tests needed.
            Keep the tests short and direct. Avoid extra helper functions unless needed.

            {rules}
        """).strip()

    def _condition_prompt(
        self,
        source_code: str,
        existing_tests: str,
        conditions: list[CompoundCondition],
        module_name: str,
    ) -> str:
        conditions_text = "\n\n".join(c.to_prompt_text() for c in conditions)
        rules = self._RULES.format(module=module_name)
        return textwrap.dedent(f"""
            You are an expert Python test engineer specialising in MC/DC coverage.

            ## Source code under test
            ```python
            {source_code}
            ```

            ## Existing test suite (DO NOT repeat these tests)
            ```python
            {existing_tests}
            ```

            ## Compound conditions requiring MC/DC coverage (from AST analysis)
            {conditions_text}

            ## Task
            Write one pytest test function per MC/DC case listed above.
            Each test must set up the inputs so that exactly one sub-condition
            independently determines the overall boolean result, as described.
            Keep the tests short and direct. Avoid extra helper functions unless needed.

            {rules}
        """).strip()

    def _combined_prompt(
        self,
        source_code: str,
        existing_tests: str,
        missing_branches: list[MissingBranch],
        conditions: list[CompoundCondition],
        module_name: str,
    ) -> str:
        branch_text = (
            "\n\n".join(b.to_prompt_text() for b in missing_branches)
            if missing_branches else "(none – focus on conditions only)"
        )
        condition_text = (
            "\n\n".join(c.to_prompt_text() for c in conditions)
            if conditions else "(none – focus on branches only)"
        )
        rules = self._RULES.format(module=module_name)
        return textwrap.dedent(f"""
            You are an expert Python test engineer specialising in white-box testing.

            ## Source code under test
            ```python
            {source_code}
            ```

            ## Existing test suite (DO NOT repeat these tests)
            ```python
            {existing_tests}
            ```

            ## Part A – Uncovered branches (coverage.py --branch)
            {branch_text}

            ## Part B – Compound conditions requiring MC/DC coverage (AST analysis)
            {condition_text}

            ## Task
            Write new pytest test functions that:
            (a) Cover every uncovered branch in Part A.
            (b) Satisfy each MC/DC case in Part B.
            Where a single test can satisfy both a branch and a condition case, do so.
            Keep the tests short and direct. Avoid comments and docstrings unless needed.

            {rules}
        """).strip()

    # ── LLM call + response parsing ───────────────────────────────────────────

    def _call_llm(self, prompt: str, targets: list[str]) -> GeneratedTests:
        endpoint = self.api_base.rstrip("/") + "/chat/completions"
        request_model = self.model.split("/", 1)[1] if "/" in self.model else self.model
        payload = {
            "model": request_model,
            "messages": [
                {"role": "system", "content": "你是一个只输出 Python 代码的测试文件生成器。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
        }
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        try:
            raw: str = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected LLM response format: {data}") from exc

        code = _strip_markdown_fences(raw)
        ok, code = _validate_syntax(code, raw)
        num_tests = _count_test_functions(code)

        return GeneratedTests(
            test_code=code,
            num_tests=num_tests,
            coverage_targets=targets,
            syntax_ok=ok,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _strip_markdown_fences(text: str) -> str:
    """Remove ``` or ```python wrappers if the LLM added them."""
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def _validate_syntax(code: str, raw: str) -> tuple[bool, str]:
    """
    Parse the generated code.  If it has a syntax error, return a
    commented-out version plus a warning header, so the pipeline
    can detect the failure without crashing.
    """
    try:
        ast.parse(code)
        return True, code
    except SyntaxError as exc:
        print(f"[TestGenerator] WARNING – LLM output has a syntax error: {exc}")
        header = f"# AUTO-GENERATED – SYNTAX ERROR: {exc}\n# Fix before running.\n\n"
        commented = "\n".join(f"# {line}" for line in raw.splitlines())
        return False, header + commented


def _count_test_functions(code: str) -> int:
    """Count how many `def test_...` functions are in the generated code."""
    try:
        tree = ast.parse(code)
        return sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        )
    except SyntaxError:
        return 0
