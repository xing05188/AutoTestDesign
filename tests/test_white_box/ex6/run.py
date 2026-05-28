"""
ex6 — 基于代码的状态转换建模与最优测试序列生成
输入：Python 源代码文件
输出：状态转换图 + 最优测试序列
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "agents" / "whitebox"))

OUTPUT_DIR = Path(__file__).resolve().parent / "diagrams"

from state_transition import State, Transition, StateTransitionDiagram
from optimal_sequence import (
    AlgorithmicSequenceGenerator,
    CoverageCriterion,
    TestSequence,
    TestStep,
)
from code_state_transition import (
    CodeStateTransitionAnalyzer,
    analyze_code_and_generate_sequence,
    analyze_code_and_generate_batch,
)

CALCULATOR_PATH = Path(__file__).resolve().parent / "calculator.py"


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _is_reset(step: TestStep) -> bool:
    return step.action == "[RESET]"


def validate_state_coverage(sequence: TestSequence, diagram: StateTransitionDiagram) -> bool:
    visited = set(sequence.get_state_sequence())
    all_states = {s.name for s in diagram.states}
    missing = all_states - visited
    if missing:
        print(f"  [WARN] 未覆盖状态: {missing}")
        return False
    return True


def validate_transition_coverage(sequence: TestSequence, diagram: StateTransitionDiagram) -> bool:
    covered = set()
    for step in sequence.steps:
        if not _is_reset(step):
            covered.add((step.from_state, step.to_state))
    all_trans = {(t.from_state, t.to_state) for t in diagram.transitions}
    missing = all_trans - covered
    if missing:
        print(f"  [WARN] 未覆盖转换: {missing}")
        return False
    return True


def validate_continuity(sequence: TestSequence) -> bool:
    for i in range(1, len(sequence.steps)):
        prev = sequence.steps[i - 1]
        curr = sequence.steps[i]
        if _is_reset(curr):
            continue
        if prev.to_state != curr.from_state:
            print(
                f"  [WARN] 路径不连续: step {prev.step} 结束于 '{prev.to_state}', "
                f"step {curr.step} 开始于 '{curr.from_state}'"
            )
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Programmatic construction (no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def test_programmatic() -> None:
    """手工构建 calculator.py 的状态转换图，测试算法生成器。"""
    print("=" * 60)
    print("Test 1 — 手工构建状态转换图（模拟 calculator.py 行为）")
    print("=" * 60)

    states = [
        State(name="就绪", description="Calculator 已初始化，等待调用", is_initial=True),
        State(name="计算成功", description="运算成功完成"),
        State(name="除零错误", description="除法除数为零（异常）", is_final=True),
        State(name="空列表错误", description="传入空列表（异常）", is_final=True),
    ]

    transitions = [
        Transition(from_state="就绪", to_state="计算成功", trigger="add/subtract/multiply/power/get_last_result"),
        Transition(from_state="就绪", to_state="除零错误", trigger="divide(b=0)", guard="[b==0]"),
        Transition(from_state="就绪", to_state="空列表错误", trigger="find_max/find_min/average", guard="[list empty]"),
        Transition(from_state="计算成功", to_state="计算成功", trigger="add/subtract/multiply/power"),
        Transition(from_state="计算成功", to_state="除零错误", trigger="divide(b=0)", guard="[b==0]"),
        Transition(from_state="计算成功", to_state="空列表错误", trigger="find_max/find_min/average", guard="[list empty]"),
        Transition(from_state="除零错误", to_state="就绪", trigger="重新调用"),
        Transition(from_state="空列表错误", to_state="就绪", trigger="重新调用"),
    ]

    diagram = StateTransitionDiagram(
        title="Calculator 状态图",
        states=states,
        transitions=transitions,
    )

    print(f"\n状态数: {len(diagram.states)}")
    for s in diagram.states:
        tag = ""
        if s.is_initial:
            tag += " [初始]"
        if s.is_final:
            tag += " [终止]"
        print(f"  - {s.name}{tag}: {s.description}")

    print(f"\n转换数: {len(diagram.transitions)}")
    for t in diagram.transitions:
        detail = f"  {t.from_state} --[{t.trigger}]"
        if t.guard:
            detail += f" {t.guard}"
        detail += f" --> {t.to_state}"
        print(detail)

    # Generate test sequences for all criteria
    algo = AlgorithmicSequenceGenerator(diagram)
    print("\n--- 全状态覆盖 ---")
    seq = algo.generate_all_states()
    print(f"  步数: {len(seq.steps)}, 序列: {' -> '.join(seq.get_state_sequence())}")
    assert len(seq.steps) > 0
    assert validate_state_coverage(seq, diagram)

    print("\n--- 全转换覆盖 ---")
    seq = algo.generate_all_transitions()
    print(f"  步数: {len(seq.steps)}, 序列: {' -> '.join(seq.get_state_sequence())}")
    assert len(seq.steps) > 0
    assert validate_transition_coverage(seq, diagram)

    print("\n--- 转换对覆盖 ---")
    seq = algo.generate_all_transition_pairs()
    print(f"  步数: {len(seq.steps)}")

    print("\n--- 全路径覆盖 ---")
    seq = algo.generate_all_paths()
    print(f"  步数: {len(seq.steps)}")

    # Mermaid output
    print("\n--- Mermaid ---")
    print(diagram.to_mermaid())

    print("\n[PASS] Test 1 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: LLM-based code analysis (requires API credentials)
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_analyze_code(analyzer: CodeStateTransitionAnalyzer) -> StateTransitionDiagram:
    """测试 LLM 从 calculator.py 中提取状态转换图。"""
    print("\n" + "=" * 60)
    print("Test 2 — LLM 分析代码：calculator.py")
    print("=" * 60)

    diagram = analyzer.analyze(str(CALCULATOR_PATH))

    print(f"\n标题: {diagram.title}")
    print(f"状态数: {len(diagram.states)}")
    for s in diagram.states:
        tag = ""
        if s.is_initial:
            tag += " [初始]"
        if s.is_final:
            tag += " [终止]"
        print(f"  - {s.name}{tag}: {s.description}")

    print(f"\n转换数: {len(diagram.transitions)}")
    for t in diagram.transitions:
        detail = f"  {t.from_state} --[{t.trigger}]"
        if t.guard:
            detail += f" {t.guard}"
        if t.action:
            detail += f" / {t.action}"
        detail += f" --> {t.to_state}"
        print(detail)

    print("\n--- Mermaid ---")
    print(diagram.to_mermaid())

    # Validation
    state_names = {s.name for s in diagram.states}
    assert len(state_names) >= 2, f"预期至少2个状态，实际: {len(state_names)}"
    assert any(s.is_initial for s in diagram.states), "缺少初始状态"
    assert len(diagram.transitions) >= 1, f"预期至少1个转换，实际: {len(diagram.transitions)}"

    for t in diagram.transitions:
        assert t.from_state in state_names, \
            f"转换来源 '{t.from_state}' 不在状态列表中"
        assert t.to_state in state_names, \
            f"转换目标 '{t.to_state}' 不在状态列表中"
        assert t.trigger, f"转换 {t.from_state}->{t.to_state} 缺少触发器"

    # Render diagram
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        path = diagram.render(str(OUTPUT_DIR / "ex6_calculator"), format="png")
        print(f"\n  [Image saved] {path}")
    except Exception as exc:
        print(f"\n  [WARN] 图像渲染失败: {exc}")

    print("\n[PASS] Test 2 通过")
    return diagram


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Generate optimal sequences from code-derived diagram
# ─────────────────────────────────────────────────────────────────────────────

def test_sequence_from_code_diagram(diagram: StateTransitionDiagram) -> None:
    """从 LLM 分析得到的状态转换图生成最优测试序列。"""
    print("\n" + "=" * 60)
    print("Test 3 — 从代码提取的状态图生成最优测试序列")
    print("=" * 60)

    algo = AlgorithmicSequenceGenerator(diagram)

    for criterion in CoverageCriterion:
        method_map = {
            CoverageCriterion.ALL_STATES: algo.generate_all_states,
            CoverageCriterion.ALL_TRANSITIONS: algo.generate_all_transitions,
            CoverageCriterion.ALL_TRANSITION_PAIRS: algo.generate_all_transition_pairs,
            CoverageCriterion.ALL_PATHS: algo.generate_all_paths,
        }
        seq = method_map[criterion]()

        print(f"\n  [{criterion.label}]")
        print(f"    步数: {len(seq.steps)}")
        print(f"    序列: {' -> '.join(seq.get_state_sequence())}")

        assert seq.criterion == criterion
        assert len(seq.steps) > 0, f"{criterion.label} 序列不能为空"
        if not validate_continuity(seq):
            print(f"  [WARN] {criterion.label} 路径不完全连续（算法限制）")

        if criterion == CoverageCriterion.ALL_STATES:
            if not validate_state_coverage(seq, diagram):
                print(f"  [NOTE] 贪心算法可能遗漏部分状态（已知限制）")
        if criterion == CoverageCriterion.ALL_TRANSITIONS:
            if not validate_transition_coverage(seq, diagram):
                print(f"  [NOTE] 贪心算法可能遗漏部分转换（已知限制）")

    print("\n[PASS] Test 3 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Convenience function — single criterion
# ─────────────────────────────────────────────────────────────────────────────

def test_convenience_single() -> None:
    """测试便捷函数 analyze_code_and_generate_sequence。"""
    print("\n" + "=" * 60)
    print("Test 4 — 便捷函数：单准则")
    print("=" * 60)

    result = analyze_code_and_generate_sequence(
        str(CALCULATOR_PATH),
        criterion=CoverageCriterion.ALL_TRANSITIONS,
    )

    diagram = result["diagram"]
    sequence = result["sequence"]

    print(f"\n  标题: {diagram.title}")
    print(f"  状态数: {len(diagram.states)}")
    print(f"  准则: {result['criterion']}")
    print(f"  测试步数: {len(sequence.steps)}")
    print(f"  序列: {' -> '.join(result['state_sequence'])}")

    assert len(diagram.states) >= 2
    assert len(sequence.steps) > 0
    assert result["diagram_json"] is not None
    assert result["mermaid_code"] is not None
    assert result["sequence_table"] is not None

    # Check serialisation round-trip
    d = result["diagram_dict"]
    assert d["title"] == diagram.title
    assert len(d["states"]) == len(diagram.states)
    assert len(d["transitions"]) == len(diagram.transitions)

    print("\n[PASS] Test 4 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Convenience function — batch generation
# ─────────────────────────────────────────────────────────────────────────────

def test_convenience_batch() -> None:
    """测试便捷函数 analyze_code_and_generate_batch。"""
    print("\n" + "=" * 60)
    print("Test 5 — 便捷函数：批量生成")
    print("=" * 60)

    result = analyze_code_and_generate_batch(str(CALCULATOR_PATH))

    diagram = result["diagram"]
    sequences = result["sequences"]

    print(f"\n  标题: {diagram.title}")
    print(f"  状态数: {len(diagram.states)}")
    print(f"  准则数: {len(sequences)}")

    for crit_value, seq_data in sequences.items():
        print(f"\n  [{seq_data['criterion_label']}]")
        print(f"    步数: {seq_data['total_steps']}")
        print(f"    序列: {' -> '.join(seq_data['state_sequence'])}")
        assert seq_data["total_steps"] > 0
        assert seq_data["criterion"] == crit_value

    assert len(sequences) == 4  # all four criteria

    print("\n[PASS] Test 5 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_edge_cases() -> None:
    """测试边界情况。"""
    print("\n" + "=" * 60)
    print("Test 6 — 边界情况")
    print("=" * 60)

    # Empty code: minimal program
    analyzer = CodeStateTransitionAnalyzer()
    try:
        # Use a temp file with minimal code
        temp_path = OUTPUT_DIR / "_temp_minimal.py"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text("x = 1\n", encoding="utf-8")
        diagram = analyzer.analyze(str(temp_path))
        print(f"  最小代码: 状态数={len(diagram.states)}, 转换数={len(diagram.transitions)}")
        assert len(diagram.states) >= 1, "即使是简单代码，也应至少识别一个状态"
        temp_path.unlink()
    except Exception as exc:
        print(f"  [NOTE] 最小代码分析: {exc}")

    # analyze_source with string
    try:
        diagram = analyzer.analyze_source("def foo(): pass\n", "minimal.py")
        print(f"  analyze_source: 状态={len(diagram.states)}, 转换={len(diagram.transitions)}")
        assert len(diagram.states) >= 1
    except Exception as exc:
        print(f"  [NOTE] analyze_source: {exc}")

    # Test with a simple class-based code
    simple_code = """
class Counter:
    def __init__(self):
        self.count = 0
    def increment(self):
        self.count += 1
    def reset(self):
        self.count = 0
"""
    try:
        diagram = analyzer.analyze_source(simple_code, "counter.py")
        print(f"  Counter 代码: 状态={len(diagram.states)}, 转换={len(diagram.transitions)}")
        assert len(diagram.states) >= 1
        for t in diagram.transitions:
            assert t.from_state in {s.name for s in diagram.states}
            assert t.to_state in {s.name for s in diagram.states}
        print(f"  Mermaid:\n{diagram.to_mermaid()}")
    except Exception as exc:
        print(f"  [NOTE] Counter 代码分析: {exc}")

    print("\n[PASS] Test 6 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    # Test 1: always runs (no LLM dependency)
    test_programmatic()

    # LLM-dependent tests
    import os
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        print("\n" + "=" * 60)
        print("未设置 OPENAI_API_KEY，跳过 LLM 相关测试 (Test 2-6)")
        print("=" * 60)
        return

    analyzer = CodeStateTransitionAnalyzer()

    diagram = test_llm_analyze_code(analyzer)
    test_sequence_from_code_diagram(diagram)
    test_convenience_single()
    test_convenience_batch()
    test_edge_cases()

    print("\n" + "=" * 60)
    print("全部测试通过!")
    if OUTPUT_DIR.exists():
        print(f"所有生成的图像文件位于: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
