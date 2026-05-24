"""
optimal_sequence.py
===================
LLM-based optimal test sequence generation from state transition diagrams.

Given a state transition diagram and a coverage criterion, this module:
1. Sends the diagram structure and coverage criterion to an LLM.
2. The LLM analyses the graph and returns the optimal (shortest) test sequence
   that satisfies the specified coverage criterion.
3. Returns a structured ``TestSequence`` object.

Supported coverage criteria
---------------------------
- ``all_states``       — visit every state at least once
- ``all_transitions``  — traverse every transition at least once
- ``all_transition_pairs`` — cover every adjacent pair of transitions
- ``all_paths``        — cover all acyclic paths from initial to final states

Typical usage
-------------
    from state_transition import StateTransitionDiagram
    from optimal_sequence import OptimalSequenceGenerator, CoverageCriterion

    generator = OptimalSequenceGenerator()
    sequence = generator.generate(diagram, CoverageCriterion.ALL_TRANSITIONS)
    print(sequence.to_table())
"""
from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from state_transition import StateTransitionDiagram


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class CoverageCriterion(str, Enum):
    """Coverage criteria for state-transition testing."""
    ALL_STATES = "all_states"
    ALL_TRANSITIONS = "all_transitions"
    ALL_TRANSITION_PAIRS = "all_transition_pairs"
    ALL_PATHS = "all_paths"

    @property
    def label(self) -> str:
        """Human-readable Chinese label."""
        _labels = {
            "all_states": "全状态覆盖",
            "all_transitions": "全转换覆盖",
            "all_transition_pairs": "转换对覆盖",
            "all_paths": "全路径覆盖",
        }
        return _labels.get(self.value, self.value)

    @property
    def description(self) -> str:
        """One-line explanation of the criterion."""
        _descs = {
            "all_states": "访问每一个状态至少一次",
            "all_transitions": "遍历每一条转换至少一次",
            "all_transition_pairs": "覆盖所有相邻的转换对（长度为2的转换序列）",
            "all_paths": "覆盖从初始状态到终止状态的所有无环路径",
        }
        return _descs.get(self.value, "")


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestStep:
    """A single step in a test sequence."""

    step: int
    action: str           # trigger / event to fire
    from_state: str
    to_state: str
    guard: str = ""       # condition that must hold
    expected: str = ""    # expected result / state


@dataclass
class TestSequence:
    """Ordered sequence of test steps generated from a state transition diagram."""

    criterion: CoverageCriterion
    diagram_title: str
    steps: list[TestStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return {
            "criterion": self.criterion.value,
            "criterion_label": self.criterion.label,
            "diagram_title": self.diagram_title,
            "total_steps": len(self.steps),
            "steps": [
                {
                    "step": s.step,
                    "action": s.action,
                    "from_state": s.from_state,
                    "to_state": s.to_state,
                    "guard": s.guard,
                    "expected": s.expected,
                }
                for s in self.steps
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Return a pretty-printed JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_table(self) -> str:
        """Return a formatted Markdown table of the test sequence."""
        lines = [
            f"# Test Sequence: {self.diagram_title}",
            f"**Coverage criterion**: {self.criterion.label} ({self.criterion.description})",
            f"**Total steps**: {len(self.steps)}",
            "",
            "| Step | Action | From | To | Guard | Expected |",
            "|------|--------|------|----|-------|----------|",
        ]
        for s in self.steps:
            lines.append(
                f"| {s.step} "
                f"| {s.action} "
                f"| {s.from_state} "
                f"| {s.to_state} "
                f"| {s.guard or '-'} "
                f"| {s.expected or s.to_state} |"
            )
        return "\n".join(lines)

    def to_text(self) -> str:
        """Return a plain-text summary of the sequence."""
        lines = [
            f"Test Sequence: {self.diagram_title}",
            f"Criterion: {self.criterion.label} ({self.criterion.description})",
            f"Total steps: {len(self.steps)}",
            "",
        ]
        for s in self.steps:
            detail = f"  {s.step}. [{s.action}] {s.from_state} --> {s.to_state}"
            if s.guard:
                detail += f"  [{s.guard}]"
            if s.expected:
                detail += f"  -> {s.expected}"
            lines.append(detail)
        return "\n".join(lines)

    def get_state_sequence(self) -> list[str]:
        """Return the ordered list of states visited in this sequence."""
        if not self.steps:
            return []
        states = [self.steps[0].from_state]
        for s in self.steps:
            states.append(s.to_state)
        return states


# ─────────────────────────────────────────────────────────────────────────────
# Main generator class
# ─────────────────────────────────────────────────────────────────────────────

class OptimalSequenceGenerator:
    """
    LLM-powered generator that produces optimal test sequences from a
    state transition diagram.

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
        你是一个软件测试专家，专门从状态转换图生成最优测试序列。

        你的任务：
        1. 分析给定的状态转换图（包含状态列表和转换列表）。
        2. 根据指定的覆盖准则，找到满足该准则的最短测试序列。
        3. 测试序列中的每一步都是一次状态转换，包含触发事件、来源状态、目标状态。

        覆盖准则说明：
        - all_states（全状态覆盖）：访问每一个状态至少一次。
        - all_transitions（全转换覆盖）：遍历每一条转换至少一次。
        - all_transition_pairs（转换对覆盖）：覆盖所有相邻的转换对（连续的两条转换）。
        - all_paths（全路径覆盖）：覆盖从初始状态到终止状态的所有无环路径。

        算法提示：
        - 对于 all_states，可以视作图遍历问题，使用 BFS/DFS 找到访问所有状态的最短路径。
        - 对于 all_transitions，可以视作中国邮递员问题，找到覆盖所有边的最短路径。
        - 对于 all_transition_pairs，枚举所有长度为 2 的转换序列并串联它们。
        - 对于 all_paths，枚举从初始状态到终止状态的所有无环路径。

        输出必须是严格的 JSON 格式：
        ```json
        {
          "criterion": "all_states",
          "diagram_title": "图标题",
          "reasoning": "简短的推理过程（1-2句话）",
          "steps": [
            {
              "step": 1,
              "action": "触发事件名称",
              "from_state": "来源状态",
              "to_state": "目标状态",
              "guard": "守卫条件（可选，没有则为空字符串）",
              "expected": "预期结果（可选，没有则为空字符串）"
            }
          ]
        }
        ```

        重要规则：
        1. 步骤编号从 1 开始，连续递增。
        2. 每一步的 from_state 必须与上一步的 to_state 相同（路径必须连续）。
        3. 每一步的 action 必须对应图中实际存在的转换。
        4. 确保覆盖准则被完整满足，不要遗漏。
        5. 优先选择最短的序列。
        6. 只输出 JSON，不要添加任何解释性文字。""")

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
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

    def generate(
        self,
        diagram: StateTransitionDiagram | dict,
        criterion: CoverageCriterion = CoverageCriterion.ALL_TRANSITIONS,
    ) -> TestSequence:
        """
        Generate the optimal test sequence for a state transition diagram.

        Parameters
        ----------
        diagram : StateTransitionDiagram or dict
            The state transition diagram to generate tests for.
            If a dict is passed, it must contain ``states`` and ``transitions`` keys.
        criterion : CoverageCriterion
            The coverage criterion to satisfy.

        Returns
        -------
        TestSequence
            Ordered test steps satisfying the criterion.
        """
        if isinstance(diagram, dict):
            graph_dict = diagram
            title = diagram.get("title", "State Diagram")
        else:
            graph_dict = diagram.to_dict()
            title = diagram.title

        prompt = self._build_prompt(graph_dict, criterion)
        raw_json = self._call_llm(prompt)
        return self._parse_response(raw_json, criterion, title)

    def generate_from_json(
        self,
        json_path: str,
        criterion: CoverageCriterion = CoverageCriterion.ALL_TRANSITIONS,
    ) -> TestSequence:
        """
        Read a state transition diagram from a JSON file and generate tests.

        Parameters
        ----------
        json_path : str
            Path to a JSON file produced by ``StateTransitionDiagram.to_json()``.
        criterion : CoverageCriterion

        Returns
        -------
        TestSequence
        """
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        return self.generate(data, criterion)

    def batch_generate(
        self,
        diagram: StateTransitionDiagram | dict,
        criteria: list[CoverageCriterion] | None = None,
    ) -> dict[CoverageCriterion, TestSequence]:
        """
        Generate test sequences for multiple coverage criteria at once.

        Parameters
        ----------
        diagram : StateTransitionDiagram or dict
        criteria : list of CoverageCriterion
            Defaults to all four criteria.

        Returns
        -------
        dict mapping each criterion to its TestSequence.
        """
        if criteria is None:
            criteria = list(CoverageCriterion)

        results: dict[CoverageCriterion, TestSequence] = {}
        for c in criteria:
            results[c] = self.generate(diagram, c)
        return results

    # ── private methods ─────────────────────────────────────────────────────

    def _build_prompt(
        self,
        graph_dict: dict,
        criterion: CoverageCriterion,
    ) -> str:
        graph_json = json.dumps(graph_dict, ensure_ascii=False, indent=2)
        return textwrap.dedent(f"""\
            请根据以下状态转换图和覆盖准则，生成最优测试序列。

            ## 状态转换图
            ```json
            {graph_json}
            ```

            ## 覆盖准则
            {criterion.value} — {criterion.label}：{criterion.description}

            ## 任务
            找到满足上述覆盖准则的最短测试序列，按 JSON 格式输出。""")

    def _call_llm(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError(
                "OpenAI-compatible API key required. "
                "Pass api_key= or set OPENAI_API_KEY."
            )

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
            "temperature": 0.1,
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
    def _parse_response(
        raw: str,
        criterion: CoverageCriterion,
        title: str,
    ) -> TestSequence:
        json_str = _extract_json(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Failed to parse LLM output as JSON.\n"
                f"Raw output:\n{raw[:2000]}"
            ) from exc

        steps = [
            TestStep(
                step=s["step"],
                action=s.get("action", ""),
                from_state=s.get("from_state", ""),
                to_state=s.get("to_state", ""),
                guard=s.get("guard", ""),
                expected=s.get("expected", s.get("to_state", "")),
            )
            for s in data.get("steps", [])
        ]

        return TestSequence(
            criterion=criterion,
            diagram_title=data.get("diagram_title", title),
            steps=steps,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Algorithmic fallback — no LLM required
# ─────────────────────────────────────────────────────────────────────────────

class AlgorithmicSequenceGenerator:
    """
    Pure-algorithmic test sequence generator (no LLM dependency).

    Uses classic graph algorithms to compute test sequences for each
    coverage criterion directly.
    """

    def __init__(self, diagram: StateTransitionDiagram | dict) -> None:
        # Normalise to internal dict format
        if isinstance(diagram, dict):
            raw_states: list[dict] = diagram.get("states", [])
            self.transitions = list(diagram.get("transitions", []))
            self.title = diagram.get("title", "State Diagram")
        else:
            raw_states = [
                {
                    "name": s.name,
                    "is_initial": s.is_initial,
                    "is_final": s.is_final,
                    "description": getattr(s, "description", ""),
                }
                for s in diagram.states
            ]
            self.transitions = [
                {
                    "from": t.from_state, "to": t.to_state,
                    "trigger": t.trigger, "guard": t.guard, "action": t.action,
                }
                for t in diagram.transitions
            ]
            self.title = diagram.title

        self.states: dict[str, dict] = {s["name"]: s for s in raw_states}

        self._adj: dict[str, list[dict]] = {}
        self._build_adjacency()

    def _build_adjacency(self) -> None:
        """Build adjacency list from transitions."""
        self._adj = {}
        for t in self.transitions:
            f = t["from"]
            if f not in self._adj:
                self._adj[f] = []
            self._adj[f].append(t)

    # ── all_states : BFS-based state covering walk ─────────────────────────

    def generate_all_states(self) -> TestSequence:
        """Find a walk that visits every state at least once (BFS + greedy)."""
        if not self.states:
            return TestSequence(
                criterion=CoverageCriterion.ALL_STATES,
                diagram_title=self.title,
            )

        initial = next(
            (name for name, s in self.states.items() if s.get("is_initial", False)),
            next(iter(self.states)),
        )

        visited: set[str] = set()
        steps: list[TestStep] = []
        current = initial
        visited.add(current)
        step_no = 0

        while len(visited) < len(self.states):
            # BFS from current to find nearest unvisited state
            path_to_new = self._shortest_path_to_unvisited(current, visited)
            if not path_to_new:
                break

            for t in path_to_new:
                step_no += 1
                steps.append(TestStep(
                    step=step_no,
                    action=t.get("trigger", ""),
                    from_state=t["from"],
                    to_state=t["to"],
                    guard=t.get("guard", ""),
                    expected=t["to"],
                ))
                visited.add(t["to"])
            current = steps[-1].to_state if steps else initial

        return TestSequence(
            criterion=CoverageCriterion.ALL_STATES,
            diagram_title=self.title,
            steps=steps,
        )

    def _shortest_path_to_unvisited(
        self, start: str, visited: set[str],
    ) -> list[dict] | None:
        """BFS to find the shortest transition path to an unvisited state."""
        from collections import deque

        queue: deque[tuple[str, list[dict]]] = deque()
        queue.append((start, []))
        seen: set[str] = {start}

        while queue:
            node, path = queue.popleft()
            if node not in visited and node != start:
                return path
            for t in self._adj.get(node, []):
                nxt = t["to"]
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, path + [t]))
        return None

    # ── all_transitions : greedy edge covering ─────────────────────────────

    def generate_all_transitions(self) -> TestSequence:
        """Cover every transition at least once using a greedy algorithm.

        When the current state has no path to any uncovered transition,
        the sequence resets to the initial state and continues.
        """
        if not self.transitions:
            return TestSequence(
                criterion=CoverageCriterion.ALL_TRANSITIONS,
                diagram_title=self.title,
            )

        uncovered: list[dict] = list(self.transitions)
        initial = self._find_start_state()
        current = initial
        steps: list[TestStep] = []
        step_no = 0

        while uncovered:
            # Select nearest uncovered transition reachable from current
            best_target, best_path = self._find_nearest_uncovered(current, uncovered)

            # If no path from current, reset to initial and try again
            if best_target is None and current != initial:
                step_no += 1
                steps.append(TestStep(
                    step=step_no,
                    action="[RESET]",
                    from_state=current,
                    to_state=initial,
                    guard="",
                    expected=initial,
                ))
                current = initial
                best_target, best_path = self._find_nearest_uncovered(current, uncovered)

            if best_target is None:
                break

            # Pop the target first to avoid index drift from path removal
            uncovered.remove(best_target)

            # Walk to the target's source state
            for t in best_path:
                step_no += 1
                steps.append(TestStep(
                    step=step_no,
                    action=t.get("trigger", ""),
                    from_state=t["from"],
                    to_state=t["to"],
                    guard=t.get("guard", ""),
                    expected=t["to"],
                ))
                if t in uncovered:
                    uncovered.remove(t)

            # Execute the target transition
            step_no += 1
            steps.append(TestStep(
                step=step_no,
                action=best_target.get("trigger", ""),
                from_state=best_target["from"],
                to_state=best_target["to"],
                guard=best_target.get("guard", ""),
                expected=best_target["to"],
            ))
            current = best_target["to"]

        return TestSequence(
            criterion=CoverageCriterion.ALL_TRANSITIONS,
            diagram_title=self.title,
            steps=steps,
        )

    def _find_nearest_uncovered(
        self, current: str, uncovered: list[dict],
    ) -> tuple[dict | None, list[dict]]:
        """Find the uncovered transition closest to *current*.

        Returns ``(target_transition, path_to_its_source)`` or
        ``(None, [])`` if nothing is reachable.
        """
        best_dist = float("inf")
        best_target: dict | None = None
        best_path: list[dict] = []

        for t in uncovered:
            path = self._shortest_path(current, t["from"])
            if path is not None and len(path) < best_dist:
                best_dist = len(path)
                best_target = t
                best_path = path

        return best_target, best_path

    def _shortest_path(
        self, start: str, target: str,
    ) -> list[dict] | None:
        """BFS to find the shortest transition path between two states."""
        from collections import deque

        if start == target:
            return []

        queue: deque[tuple[str, list[dict]]] = deque()
        queue.append((start, []))
        seen: set[str] = {start}

        while queue:
            node, path = queue.popleft()
            for t in self._adj.get(node, []):
                nxt = t["to"]
                if nxt == target:
                    return path + [t]
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, path + [t]))
        return None

    def _find_start_state(self) -> str:
        """Find the initial state, or return the first state."""
        for name, s in self.states.items():
            if s.get("is_initial", False):
                return name
        return next(iter(self.states)) if self.states else ""

    # ── all_transition_pairs : enumerate and chain ─────────────────────────

    def generate_all_transition_pairs(self) -> TestSequence:
        """Cover every adjacent pair of transitions."""
        pairs: list[tuple[dict, dict]] = []
        for t1 in self.transitions:
            for t2 in self.transitions:
                if t1["to"] == t2["from"]:
                    pairs.append((t1, t2))

        if not pairs:
            return TestSequence(
                criterion=CoverageCriterion.ALL_TRANSITION_PAIRS,
                diagram_title=self.title,
            )

        steps: list[TestStep] = []
        step_no = 0
        current = self._find_start_state()
        covered: set[int] = set()

        while len(covered) < len(pairs):
            best_pair_idx = -1
            best_path: list[dict] = []
            best_dist = float("inf")

            for idx, (t1, t2) in enumerate(pairs):
                if idx in covered:
                    continue
                path = self._shortest_path(current, t1["from"])
                if path is not None and len(path) < best_dist:
                    best_dist = len(path)
                    best_path = path
                    best_pair_idx = idx

            if best_pair_idx < 0:
                break

            # Walk to the pair
            for t in best_path:
                step_no += 1
                steps.append(TestStep(
                    step=step_no,
                    action=t.get("trigger", ""),
                    from_state=t["from"],
                    to_state=t["to"],
                    guard=t.get("guard", ""),
                    expected=t["to"],
                ))

            # Execute the pair
            t1, t2 = pairs[best_pair_idx]
            step_no += 1
            steps.append(TestStep(
                step=step_no,
                action=t1.get("trigger", ""),
                from_state=t1["from"],
                to_state=t1["to"],
                guard=t1.get("guard", ""),
                expected=t1["to"],
            ))
            step_no += 1
            steps.append(TestStep(
                step=step_no,
                action=t2.get("trigger", ""),
                from_state=t2["from"],
                to_state=t2["to"],
                guard=t2.get("guard", ""),
                expected=t2["to"],
            ))
            current = t2["to"]
            covered.add(best_pair_idx)

        return TestSequence(
            criterion=CoverageCriterion.ALL_TRANSITION_PAIRS,
            diagram_title=self.title,
            steps=steps,
        )

    # ── all_paths : DFS enumeration ────────────────────────────────────────

    def generate_all_paths(self) -> TestSequence:
        """Enumerate all acyclic paths from initial to final states."""
        initial = self._find_start_state()
        final_states: set[str] = {
            name for name, s in self.states.items()
            if s.get("is_final", False)
        }
        # If no explicit final states, treat sink states (no outgoing edges)
        # as implicit final states
        if not final_states:
            final_states = {
                name for name in self.states
                if name not in self._adj or len(self._adj[name]) == 0
            }

        all_paths = self._enumerate_acyclic_paths(initial, final_states)

        steps: list[TestStep] = []
        step_no = 0

        # Chain paths together: after each path, walk back to initial
        # for the next path (if possible), or just concatenate.
        current = initial
        for path_transitions in all_paths:
            if not path_transitions:
                continue

            # Walk from current to the start of this path
            walk = self._shortest_path(current, path_transitions[0]["from"])
            if walk:
                for t in walk:
                    step_no += 1
                    steps.append(TestStep(
                        step=step_no,
                        action=t.get("trigger", ""),
                        from_state=t["from"],
                        to_state=t["to"],
                        guard=t.get("guard", ""),
                        expected=t["to"],
                    ))
                    current = t["to"]

            for t in path_transitions:
                step_no += 1
                steps.append(TestStep(
                    step=step_no,
                    action=t.get("trigger", ""),
                    from_state=t["from"],
                    to_state=t["to"],
                    guard=t.get("guard", ""),
                    expected=t["to"],
                ))
                current = t["to"]

        return TestSequence(
            criterion=CoverageCriterion.ALL_PATHS,
            diagram_title=self.title,
            steps=steps,
        )

    def _enumerate_acyclic_paths(
        self,
        start: str,
        finals: set[str],
    ) -> list[list[dict]]:
        """DFS to enumerate all acyclic paths from start to any final state.

        If no final states are provided, all *maximal* simple paths are
        returned (paths that end when every outgoing neighbour has already
        been visited on the current path).
        """
        result: list[list[dict]] = []

        def dfs(node: str, path: list[dict], visited: set[str]) -> None:
            if finals and node in finals and path:
                result.append(list(path))
                return

            has_unvisited_neighbour = False
            for t in self._adj.get(node, []):
                nxt = t["to"]
                if nxt not in visited:
                    has_unvisited_neighbour = True
                    visited.add(nxt)
                    path.append(t)
                    dfs(nxt, path, visited)
                    path.pop()
                    visited.discard(nxt)

            # If no finals defined, treat any maximal simple path as result
            if not finals and not has_unvisited_neighbour and path:
                result.append(list(path))

        dfs(start, [], {start})
        return result


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


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function
# ─────────────────────────────────────────────────────────────────────────────

def generate_optimal_sequence(
    diagram: StateTransitionDiagram | dict,
    criterion: CoverageCriterion = CoverageCriterion.ALL_TRANSITIONS,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    use_llm: bool = True,
) -> TestSequence:
    """
    One-shot convenience function.

    Parameters
    ----------
    diagram : StateTransitionDiagram or dict
        The state transition diagram.
    criterion : CoverageCriterion
        Coverage criterion.
    api_key / api_base / model
        Passed through to :class:`OptimalSequenceGenerator` (LLM mode only).
    use_llm : bool
        If True, use LLM; if False, use the pure-algorithmic fallback.

    Returns
    -------
    TestSequence
    """
    if use_llm:
        generator = OptimalSequenceGenerator(
            api_key=api_key,
            api_base=api_base,
            model=model,
        )
        return generator.generate(diagram, criterion)

    algo = AlgorithmicSequenceGenerator(diagram)
    _method_map = {
        CoverageCriterion.ALL_STATES: algo.generate_all_states,
        CoverageCriterion.ALL_TRANSITIONS: algo.generate_all_transitions,
        CoverageCriterion.ALL_TRANSITION_PAIRS: algo.generate_all_transition_pairs,
        CoverageCriterion.ALL_PATHS: algo.generate_all_paths,
    }
    method = _method_map.get(criterion)
    if method is None:
        raise ValueError(f"Unknown criterion: {criterion}")
    return method()
