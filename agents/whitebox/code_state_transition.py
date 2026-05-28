"""
code_state_transition.py
========================
LLM-based code behaviour modelling: extract state transition diagrams from
Python source code, then generate optimal test sequences.

Given a Python source file, this module:
1. Reads the source code.
2. Calls an LLM to extract a **structured behaviour summary** (not raw states).
3. Deterministically renders the summary into natural-language requirements.
4. Feeds the requirements into ``StateTransitionAnalyzer`` to produce a
   clean state-transition diagram.
5. Generates optimal test sequences per selected coverage criteria.

This three-step pipeline avoids the explosion that occurs when an LLM
maps code directly to fine-grained states/transitions.

Typical usage
-------------
    from code_state_transition import (
        CodeStateTransitionAnalyzer,
        analyze_code_and_generate_sequence,
    )

    analyzer = CodeStateTransitionAnalyzer()
    diagram = analyzer.analyze("calculator.py")

    from optimal_sequence import CoverageCriterion
    sequence = analyze_code_and_generate_sequence(
        "calculator.py",
        CoverageCriterion.ALL_TRANSITIONS,
    )
"""
from __future__ import annotations

import json
import os
import re
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from state_transition import StateTransitionDiagram
    from optimal_sequence import CoverageCriterion


# ─────────────────────────────────────────────────────────────────────────────
# Main analyser class
# ─────────────────────────────────────────────────────────────────────────────

class CodeStateTransitionAnalyzer:
    """
    LLM-powered analyser that reads Python source code and produces a
    state-transition diagram.

    The pipeline has three steps:
    1. LLM extracts a **behaviour summary** (normal / exceptional / stateful).
    2. The summary is deterministically rendered into requirement text.
    3. ``StateTransitionAnalyzer`` converts the requirement text into a
       clean state-transition diagram.

    This avoids the explosion of fine-grained states that occurs when an
    LLM maps code directly to states/transitions.

    Parameters
    ----------
    api_key : str
        OpenAI-compatible API key. Defaults to ``OPENAI_API_KEY`` env var.
    api_base : str
        Base URL of the chat/completions endpoint.
    model : str
        Model identifier.
    max_tokens : int
        Maximum tokens in the LLM response.
    """

    # Prompt for step 1: extract a high-level behaviour summary.
    # The LLM describes *what the code does*, not how many states it has.
    _BEHAVIOUR_PROMPT = textwrap.dedent("""\
        你是一个代码行为分析专家。请仔细阅读以下 Python 源代码，
        提取系统的高层行为摘要，不要直接建模状态。

        你需要识别三类行为：
        1. **normal** — 正常的、成功的操作路径。
           例如：add/subtract/multiply 正常执行并返回结果。
        2. **exceptional** — 异常、错误或边界情况。
           例如：除零错误、空列表、类型错误等。
        3. **stateful** — 跨调用的状态记忆或副作用。
           例如：last_result 保存了上一次成功运算的结果。

        输出必须是严格的 JSON 格式：
        ```json
        {
          "title": "系统名称",
          "behaviors": [
            {
              "type": "normal",
              "operations": ["op1", "op2"],
              "description": "这些操作正常执行时的行为描述",
              "precondition": "",
              "outcome": "正常执行后的结果"
            },
            {
              "type": "exceptional",
              "operations": ["op1"],
              "description": "触发异常的条件的描述",
              "precondition": "触发异常的条件",
              "outcome": "异常的结果（如抛出什么异常）"
            },
            {
              "type": "stateful",
              "field": "字段名或变量名",
              "operations": [],
              "description": "该状态信息如何影响系统行为",
              "precondition": "",
              "outcome": ""
            }
          ]
        }
        ```

        重要规则：
        1. 合并相似行为：多个正常操作如果行为一致，归入同一个 normal 条目。
        2. 不要遗漏异常路径：每个可能抛出异常的路径都要有对应的 exceptional 条目。
        3. 识别跨调用的状态：self.xxx、全局变量等跨调用记忆的状态需要 stateful 条目。
        4. 每个条目描述应简洁、准确，不可虚构代码中没有的行为。
        5. 只输出 JSON，不要添加任何解释性文字。""")

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "OpenAI-compatible API key required. "
                "Pass api_key= or set OPENAI_API_KEY."
            )
        self.api_base = (
            api_base
            or os.environ.get(
                "OPENAI_API_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        ).rstrip("/")
        self.model = model or os.environ.get("OPENAI_MODEL", "qwen-plus")
        self.max_tokens = max_tokens

    # ── public API ──────────────────────────────────────────────────────────

    def analyze(self, code_path: str) -> StateTransitionDiagram:
        """
        Analyse Python source code and produce a state-transition diagram.

        Parameters
        ----------
        code_path : str
            Path to a Python source file.

        Returns
        -------
        StateTransitionDiagram
        """
        source_code = Path(code_path).read_text(encoding="utf-8")
        file_name = Path(code_path).name

        # Step 1: code → behaviour summary (LLM)
        behaviours = self._extract_behaviours(source_code, file_name)

        # Step 2: behaviour summary → requirement text (deterministic)
        requirement_text = _behaviours_to_requirement(behaviours)

        # Step 3: requirement text → state-transition diagram (LLM)
        from state_transition import StateTransitionAnalyzer

        req_analyzer = StateTransitionAnalyzer(
            api_key=self.api_key,
            api_base=self.api_base,
            model=self.model,
            max_tokens=self.max_tokens,
        )
        return req_analyzer.analyze(requirement_text)

    def analyze_source(self, source_code: str, file_name: str = "code.py") -> StateTransitionDiagram:
        """
        Analyse Python source code given as a string.

        Parameters
        ----------
        source_code : str
            Python source code as a string.
        file_name : str
            A label for the code (used in the diagram title).

        Returns
        -------
        StateTransitionDiagram
        """
        behaviours = self._extract_behaviours(source_code, file_name)
        requirement_text = _behaviours_to_requirement(behaviours)

        from state_transition import StateTransitionAnalyzer

        req_analyzer = StateTransitionAnalyzer(
            api_key=self.api_key,
            api_base=self.api_base,
            model=self.model,
            max_tokens=self.max_tokens,
        )
        return req_analyzer.analyze(requirement_text)

    # ── Step 1: code → behaviour summary (LLM) ──────────────────────────────

    def _extract_behaviours(self, source_code: str, file_name: str) -> dict:
        prompt = textwrap.dedent(f"""\
            请分析以下 Python 源代码（文件名: {file_name}），
            提取系统的高层行为摘要。

            ## 源代码
            ```python
            {source_code}
            ```

            ## 任务
            识别 normal（正常）、exceptional（异常）、stateful（跨调用状态）三类行为，
            输出上述 JSON 格式的行为摘要。
            严格按照 JSON 格式输出，不要输出任何额外的文字。""")

        raw = self._call_llm(prompt, system_prompt=self._BEHAVIOUR_PROMPT)
        return _parse_and_validate_behaviours(raw)

    # ── LLM call (shared implementation) ────────────────────────────────────

    def _call_llm(self, prompt: str, system_prompt: str) -> str:
        endpoint = self.api_base.rstrip("/") + "/chat/completions"
        request_model = (
            self.model.split("/", 1)[1]
            if "/" in self.model
            else self.model
        )
        payload = {
            "model": request_model,
            "messages": [
                {"role": "system", "content": system_prompt},
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
        data = response.json()

        if response.status_code >= 400:
            error_msg = data.get("error", {}).get("message", str(data))
            raise RuntimeError(
                f"LLM API error ({response.status_code}): {error_msg}"
            )

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected LLM response format: {data}"
            ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: behaviour summary → requirement text (deterministic, no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def _behaviours_to_requirement(behaviours: dict) -> str:
    """
    Deterministically render a behaviour summary into natural-language
    requirement text suitable for ``StateTransitionAnalyzer``.
    """
    title = behaviours.get("title", "系统")
    items: list[dict] = behaviours.get("behaviors", [])

    normals = [b for b in items if b.get("type") == "normal"]
    exceptionals = [b for b in items if b.get("type") == "exceptional"]
    statefuls = [b for b in items if b.get("type") == "stateful"]

    parts: list[str] = []

    # Title line
    parts.append(f"# {title} 系统需求规格说明")
    parts.append("")

    # Normal behaviours
    if normals:
        all_normal_ops: list[str] = []
        for b in normals:
            ops = b.get("operations", [])
            all_normal_ops.extend(ops)
        ops_str = "、".join(all_normal_ops) if all_normal_ops else "相关操作"
        parts.append(f"系统提供以下正常操作：{ops_str}。")

        for b in normals:
            desc = b.get("description", "")
            outcome = b.get("outcome", "")
            if desc and outcome:
                parts.append(f"- {desc}，{outcome}。")
            elif desc:
                parts.append(f"- {desc}。")
            elif outcome:
                parts.append(f"- {outcome}。")

    # Exceptional behaviours
    if exceptionals:
        parts.append("")
        parts.append("系统存在以下异常/错误情况：")
        for b in exceptionals:
            ops = b.get("operations", [])
            ops_str = "、".join(ops) if ops else "某操作"
            precondition = b.get("precondition", "")
            outcome = b.get("outcome", "")
            desc = b.get("description", "")

            line = f"- 当调用 {ops_str}"
            if precondition:
                line += f" 时，如果 {precondition}"
            line += f"，则 {outcome or desc}。"
            parts.append(line)

    # Stateful behaviours
    if statefuls:
        parts.append("")
        parts.append("系统存在以下跨调用状态：")
        for b in statefuls:
            field = b.get("field", "某状态")
            desc = b.get("description", "")
            parts.append(f"- {field}：{desc}。")

    parts.append("")
    parts.append("请根据以上需求规格说明，提取系统的状态转换图。")

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions — full pipeline
# ─────────────────────────────────────────────────────────────────────────────

def analyze_code_and_generate_sequence(
    code_path: str,
    criterion: CoverageCriterion | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    use_llm: bool = True,
) -> dict:
    """
    One-shot convenience function: analyse code → diagram → test sequence.

    Parameters
    ----------
    code_path : str
        Path to a Python source file.
    criterion : CoverageCriterion or None
        Coverage criterion. Defaults to ALL_TRANSITIONS.
    api_key / api_base / model
        Passed through to :class:`CodeStateTransitionAnalyzer`.
    use_llm : bool
        If True, use LLM for code analysis. If False, this function
        is not useful (no fallback).

    Returns
    -------
    dict
        Keys: ``diagram``, ``sequence``, ``diagram_json``,
        ``mermaid_code``, ``image_path``, ``state_sequence``, etc.
    """
    from optimal_sequence import (
        CoverageCriterion,
        generate_optimal_sequence,
    )

    if criterion is None:
        criterion = CoverageCriterion.ALL_TRANSITIONS

    # Step 1-3: code → diagram
    analyzer = CodeStateTransitionAnalyzer(
        api_key=api_key,
        api_base=api_base,
        model=model,
    )
    diagram = analyzer.analyze(code_path)

    # Step 4: generate test sequences
    sequence = generate_optimal_sequence(diagram, criterion, use_llm=use_llm)

    result: dict = {
        "diagram": diagram,
        "diagram_json": diagram.to_json(),
        "diagram_dict": diagram.to_dict(),
        "mermaid_code": diagram.to_mermaid(),
        "sequence": sequence,
        "sequence_table": sequence.to_table(),
        "sequence_text": sequence.to_text(),
        "sequence_json": sequence.to_json(),
        "state_sequence": sequence.get_state_sequence(),
        "criterion": criterion.value,
    }

    # Optionally render diagram as image
    code_stem = Path(code_path).stem
    output_dir = Path(code_path).resolve().parent / f"{code_stem}_state_diagrams"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        image_path = diagram.render(str(output_dir / diagram.title), format="png")
        result["image_path"] = image_path
    except Exception:
        result["image_path"] = None

    return result


def analyze_code_and_generate_batch(
    code_path: str,
    criteria: list[CoverageCriterion] | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
) -> dict:
    """
    Analyse code and generate test sequences for multiple coverage criteria.

    Parameters
    ----------
    code_path : str
        Path to a Python source file.
    criteria : list of CoverageCriterion or None
        Defaults to all four criteria.
    api_key / api_base / model
        Passed through to :class:`CodeStateTransitionAnalyzer`.

    Returns
    -------
    dict
        Keys: ``diagram``, ``diagram_json``, ``mermaid_code``,
        ``sequences`` (dict mapping criterion value → TestSequence).
    """
    from optimal_sequence import CoverageCriterion, AlgorithmicSequenceGenerator

    if criteria is None:
        criteria = list(CoverageCriterion)

    # Step 1-3: code → diagram
    analyzer = CodeStateTransitionAnalyzer(
        api_key=api_key,
        api_base=api_base,
        model=model,
    )
    diagram = analyzer.analyze(code_path)

    # Step 4: generate sequences for all criteria
    algo = AlgorithmicSequenceGenerator(diagram)
    _method_map = {
        CoverageCriterion.ALL_STATES: algo.generate_all_states,
        CoverageCriterion.ALL_TRANSITIONS: algo.generate_all_transitions,
        CoverageCriterion.ALL_TRANSITION_PAIRS: algo.generate_all_transition_pairs,
        CoverageCriterion.ALL_PATHS: algo.generate_all_paths,
    }

    sequences: dict[str, dict] = {}
    for c in criteria:
        method = _method_map.get(c)
        if method is None:
            raise ValueError(f"Unknown criterion: {c}")
        seq = method()
        sequences[c.value] = {
            "criterion": c.value,
            "criterion_label": c.label,
            "test_sequence": seq,
            "table": seq.to_table(),
            "text": seq.to_text(),
            "json": seq.to_json(),
            "state_sequence": seq.get_state_sequence(),
            "total_steps": len(seq.steps),
        }

    return {
        "diagram": diagram,
        "diagram_json": diagram.to_json(),
        "diagram_dict": diagram.to_dict(),
        "mermaid_code": diagram.to_mermaid(),
        "sequences": sequences,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> str:
    """Extract the first JSON object from text that may contain extra prose
    or markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0)
    return text


_VALID_BEHAVIOUR_TYPES = {"normal", "exceptional", "stateful"}


def _parse_and_validate_behaviours(raw: str) -> dict:
    """Parse LLM output as a behaviour summary and validate its structure."""
    json_str = _extract_json(raw)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse behaviour summary JSON.\n"
            f"Raw output:\n{raw[:2000]}"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"Behaviour summary must be a JSON object, got {type(data)}")

    if "title" not in data:
        data["title"] = "Unknown"

    items = data.get("behaviors", [])
    if not isinstance(items, list) or len(items) == 0:
        raise RuntimeError("Behaviour summary must contain a non-empty 'behaviors' list")

    for i, b in enumerate(items):
        if not isinstance(b, dict):
            raise RuntimeError(f"behaviors[{i}] must be an object, got {type(b)}")
        b_type = b.get("type", "")
        if b_type not in _VALID_BEHAVIOUR_TYPES:
            raise RuntimeError(
                f"behaviors[{i}] has invalid type '{b_type}'. "
                f"Must be one of: {_VALID_BEHAVIOUR_TYPES}"
            )
        if not b.get("description"):
            raise RuntimeError(f"behaviors[{i}] is missing 'description'")
        if b_type == "stateful" and not b.get("field"):
            raise RuntimeError(
                f"behaviors[{i}] type='stateful' but missing 'field'"
            )

    return data
