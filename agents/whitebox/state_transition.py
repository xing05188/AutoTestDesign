"""
state_transition.py
===================
LLM-based state transition modelling from requirement documents.

Given a natural-language requirements document, this module:
1. Calls an LLM to extract states and transitions.
2. Produces a structured state-transition diagram.
3. Renders the diagram as a Mermaid state diagram (Markdown-ready) and/or JSON.

Typical usage
-------------
    analyzer = StateTransitionAnalyzer(
        api_key=os.environ["OPENAI_API_KEY"],
        api_base=os.environ["OPENAI_API_URL"],
        model=os.environ["OPENAI_MODEL"],
    )
    diagram = analyzer.analyze(requirements="...")
    print(diagram.to_mermaid())
    print(diagram.to_json())
"""
from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import requests


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class State:
    """A single state in the state-transition diagram."""

    name: str
    description: str = ""
    is_initial: bool = False
    is_final: bool = False
    entry_actions: list[str] = field(default_factory=list)
    exit_actions: list[str] = field(default_factory=list)


@dataclass
class Transition:
    """A directed transition between two states."""

    from_state: str
    to_state: str
    trigger: str           # event / trigger that causes the transition
    guard: str = ""        # condition that must be true, e.g. "[balance > 0]"
    action: str = ""       # action performed during the transition


@dataclass
class StateTransitionDiagram:
    """Complete state-transition model produced from a requirements document."""

    title: str
    states: list[State] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)

    # ── serialisation ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return {
            "title": self.title,
            "states": [
                {
                    "name": s.name,
                    "description": s.description,
                    "is_initial": s.is_initial,
                    "is_final": s.is_final,
                    "entry_actions": s.entry_actions,
                    "exit_actions": s.exit_actions,
                }
                for s in self.states
            ],
            "transitions": [
                {
                    "from": t.from_state,
                    "to": t.to_state,
                    "trigger": t.trigger,
                    "guard": t.guard,
                    "action": t.action,
                }
                for t in self.transitions
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Return a pretty-printed JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_mermaid(self) -> str:
        """
        Render as a Mermaid ``stateDiagram-v2`` block.

        The output is suitable for embedding in Markdown documents or
        rendering in tools that support Mermaid (GitHub, GitLab, Notion, etc.).
        """
        lines = ["stateDiagram-v2"]
        if self.title:
            lines.append(f"    title {self.title}")
        lines.append("")

        # Initial pseudo-state → first real state is handled via transitions.
        # In Mermaid stateDiagram-v2 we define states, then transitions.

        for s in self.states:
            desc = f": {s.description}" if s.description else ""
            lines.append(f"    state \"{s.name}{desc}\" as {_mermaid_id(s.name)}")

        lines.append("")

        for t in self.transitions:
            from_id = _mermaid_id(t.from_state)
            to_id = _mermaid_id(t.to_state)
            label_parts = []
            if t.trigger:
                label_parts.append(t.trigger)
            if t.guard:
                label_parts.append(t.guard)
            if t.action:
                label_parts.append(f"/ {t.action}")
            label = f" : {' '.join(label_parts)}" if label_parts else ""
            lines.append(f"    {from_id} --> {to_id}{label}")

        # Mark initial / final states
        for s in self.states:
            sid = _mermaid_id(s.name)
            if s.is_initial:
                lines.insert(1, f"    [*] --> {sid}")
            if s.is_final:
                lines.append(f"    {sid} --> [*]")

        return "\n".join(lines)

    def to_text(self) -> str:
        """Return a plain-text summary of the diagram."""
        lines = [f"State Transition Diagram: {self.title}", "=" * 50, ""]
        lines.append("States:")
        for s in self.states:
            markers = []
            if s.is_initial:
                markers.append("initial")
            if s.is_final:
                markers.append("final")
            tag = f" [{', '.join(markers)}]" if markers else ""
            lines.append(f"  - {s.name}{tag}")
            if s.description:
                lines.append(f"    {s.description}")

        lines.append("")
        lines.append("Transitions:")
        for t in self.transitions:
            detail = f"  {t.from_state} --> {t.to_state}"
            detail += f"  [{t.trigger}]"
            if t.guard:
                detail += f"  {t.guard}"
            if t.action:
                detail += f"  / {t.action}"
            lines.append(detail)

        return "\n".join(lines)

    # ── graphviz rendering ─────────────────────────────────────────────────

    def to_graphviz(self) -> "Digraph":
        """
        Return a graphviz ``Digraph`` for this state-transition diagram.

        Requires ``pip install graphviz`` plus the system Graphviz binaries.
        The returned object can be further customised or rendered directly
        via ``.render()``.
        """
        try:
            from graphviz import Digraph
        except ImportError as exc:
            raise ImportError(
                "graphviz is required for image rendering. "
                "Install with: pip install graphviz"
            ) from exc

        dot = Digraph(
            name=_safe_id(self.title),
            comment=self.title,
            format="png",
            engine="dot",
        )
        dot.attr(
            rankdir="LR",
            fontname="SimHei",
            fontsize="12",
            label=f"<<b>{self.title}</b>>" if self.title else "",
            labelloc="t",
        )
        dot.attr("node", fontname="SimHei", fontsize="10", shape="ellipse")
        dot.attr("edge", fontname="SimHei", fontsize="9")

        # Virtual start node for initial transitions
        dot.node("__start__", "", shape="point", width="0")

        for s in self.states:
            shape = "doublecircle" if s.is_final else "ellipse"
            label = f"{s.name}\\n{s.description}" if s.description else s.name
            dot.node(_safe_id(s.name), label, shape=shape)

        for t in self.transitions:
            label_parts = []
            if t.trigger:
                label_parts.append(t.trigger)
            if t.guard:
                label_parts.append(t.guard)
            if t.action:
                label_parts.append(f"/ {t.action}")
            label = "\\n".join(label_parts) if label_parts else ""
            dot.edge(
                _safe_id(t.from_state),
                _safe_id(t.to_state),
                label=label,
            )

        for s in self.states:
            if s.is_initial:
                dot.edge("__start__", _safe_id(s.name))

        return dot

    def render(
        self,
        output_path: str,
        format: str = "png",
    ) -> str:
        """
        Render the state-transition diagram to an image file.

        Parameters
        ----------
        output_path : str
            Path for the output image (e.g. ``"diagrams/login.png"``).
            Parent directories are created if they do not exist.
        format : str
            Output format: ``"png"``, ``"svg"``, ``"pdf"``, etc.

        Returns
        -------
        str
            Absolute path to the generated image.
        """
        dot = self.to_graphviz()
        dot.format = format

        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        out_stem = str(path.with_suffix(""))
        dot.render(filename=out_stem, cleanup=True)

        return str(path.with_suffix(f".{format}"))


# ─────────────────────────────────────────────────────────────────────────────
# Main analyser class
# ─────────────────────────────────────────────────────────────────────────────

class StateTransitionAnalyzer:
    """
    LLM-powered analyser that produces a state-transition diagram from
    natural-language requirements.

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

    _SYSTEM_PROMPT = textwrap.dedent("""\
        你是一个系统建模专家，专门从需求文档中提取状态转换图。
        请仔细阅读需求文档，识别出系统可能处于的所有状态，
        以及导致状态之间转换的事件（触发器）、守卫条件和动作。

        输出必须是严格的 JSON 格式，如下所示：
        ```json
        {
          "title": "系统名称",
          "states": [
            {
              "name": "状态名称",
              "description": "状态说明",
              "is_initial": true,
              "is_final": false,
              "entry_actions": [],
              "exit_actions": []
            }
          ],
          "transitions": [
            {
              "from": "源状态名称",
              "to": "目标状态名称",
              "trigger": "事件/触发器",
              "guard": "守卫条件（可选，如 [已登录]）",
              "action": "转换动作（可选）"
            }
          ]
        }
        ```

        重要规则：
        1. 每个状态名字必须唯一，且有意义。
        2. 必须有且仅有一个初始状态 (is_initial: true)。
        3. 可以有零个或多个终止状态 (is_final: true)。
        4. 每个转换必须有 trigger（触发事件），guard 和 action 可为空字符串。
        5. from 和 to 必须对应 states 中已有的状态名称。
        6. 不要遗漏任何关键状态和转换。
        7. 只输出 JSON，不要添加任何解释性文字。""")

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

    def analyze(self, requirements: str) -> StateTransitionDiagram:
        """
        Analyse requirement text and produce a state-transition diagram.

        Parameters
        ----------
        requirements : str
            Natural-language description of system behaviour.

        Returns
        -------
        StateTransitionDiagram
        """
        prompt = self._build_prompt(requirements)
        raw_json = self._call_llm(prompt)
        return self._parse_response(raw_json)

    def analyze_file(self, requirements_path: str) -> StateTransitionDiagram:
        """
        Read requirements from a file and produce a state-transition diagram.

        Parameters
        ----------
        requirements_path : str
            Path to a text file containing the requirements document.

        Returns
        -------
        StateTransitionDiagram
        """
        from pathlib import Path

        text = Path(requirements_path).read_text(encoding="utf-8")
        return self.analyze(text)

    # ── private methods ─────────────────────────────────────────────────────

    def _build_prompt(self, requirements: str) -> str:
        return textwrap.dedent(f"""\
            请根据以下需求文档，提取系统的状态转换图。

            ## 需求文档
            {requirements}

            ## 任务
            识别所有系统状态和状态转换，输出 JSON 格式的状态转换图。
            严格按照上述 JSON 格式输出，不要输出任何额外的文字。""")

    def _call_llm(self, prompt: str) -> str:
        endpoint = self.api_base.rstrip("/") + "/chat/completions"
        request_model = (
            self.model.split("/", 1)[1]
            if "/" in self.model
            else self.model
        )
        payload = {
            "model": request_model,
            "messages": [
                {"role": "system", "content": self._SYSTEM_PROMPT},
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
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected LLM response format: {data}"
            ) from exc

    @staticmethod
    def _parse_response(raw: str) -> StateTransitionDiagram:
        json_str = _extract_json(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Failed to parse LLM output as JSON.\n"
                f"Raw output:\n{raw[:2000]}"
            ) from exc

        states = [
            State(
                name=s["name"],
                description=s.get("description", ""),
                is_initial=s.get("is_initial", False),
                is_final=s.get("is_final", False),
                entry_actions=s.get("entry_actions", []),
                exit_actions=s.get("exit_actions", []),
            )
            for s in data.get("states", [])
        ]

        transitions = [
            Transition(
                from_state=t["from"],
                to_state=t["to"],
                trigger=t.get("trigger", ""),
                guard=t.get("guard", ""),
                action=t.get("action", ""),
            )
            for t in data.get("transitions", [])
        ]

        return StateTransitionDiagram(
            title=data.get("title", "State Transition Diagram"),
            states=states,
            transitions=transitions,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> str:
    """Extract the first JSON object from text that may contain extra prose
    or markdown fences."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try to find JSON object boundaries
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0)
    return text


def _mermaid_id(name: str) -> str:
    """Convert a state name to a safe Mermaid identifier."""
    return re.sub(r"[^a-zA-Z0-9_一-鿿]", "_", name)


def _safe_id(name: str) -> str:
    """Convert a state name to a safe Graphviz node identifier."""
    safe = re.sub(r"[^a-zA-Z0-9_一-鿿]", "_", name)
    if not safe or safe[0].isdigit():
        safe = "_" + safe
    return safe


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function
# ─────────────────────────────────────────────────────────────────────────────

def generate_state_transition_diagram(
    requirements: str,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
) -> StateTransitionDiagram:
    """
    One-shot convenience function.

    Parameters
    ----------
    requirements : str
        Natural-language requirements document.
    api_key / api_base / model
        Passed through to :class:`StateTransitionAnalyzer`.

    Returns
    -------
    StateTransitionDiagram
    """
    analyzer = StateTransitionAnalyzer(
        api_key=api_key,
        api_base=api_base,
        model=model,
    )
    return analyzer.analyze(requirements)
