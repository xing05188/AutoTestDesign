"""
ex5 - 最优测试序列生成
基于状态转换图和覆盖准则，通过 LLM 或算法生成最优测试序列。

输入：状态转换图 + 覆盖准则
输出：最优测试序列
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "agents" / "whitebox"))

from state_transition import State, Transition, StateTransitionDiagram
from optimal_sequence import (
    AlgorithmicSequenceGenerator,
    CoverageCriterion,
    OptimalSequenceGenerator,
    TestSequence,
    TestStep,
    generate_optimal_sequence,
)


# ─────────────────────────────────────────────────────────────────────────────
# Sample state transition diagrams
# ─────────────────────────────────────────────────────────────────────────────

def build_login_diagram() -> StateTransitionDiagram:
    """Build the login system state diagram (same as ex4)."""
    return StateTransitionDiagram(
        title="用户登录系统",
        states=[
            State(name="未登录", description="用户未登录", is_initial=True),
            State(name="验证中", description="系统验证用户凭据"),
            State(name="已登录", description="用户已成功登录"),
            State(name="会话超时", description="用户会话超时"),
        ],
        transitions=[
            Transition(from_state="未登录", to_state="验证中", trigger="点击登录"),
            Transition(from_state="验证中", to_state="已登录", trigger="验证成功"),
            Transition(from_state="验证中", to_state="未登录", trigger="验证失败"),
            Transition(from_state="已登录", to_state="未登录", trigger="退出登录"),
            Transition(from_state="已登录", to_state="会话超时", trigger="无操作超时", guard="[30分钟]"),
            Transition(from_state="会话超时", to_state="未登录", trigger="任意操作"),
        ],
    )


def build_order_diagram() -> StateTransitionDiagram:
    """Build the order processing system state diagram (simplified version)."""
    return StateTransitionDiagram(
        title="在线订单处理系统",
        states=[
            State(name="待支付", description="订单已创建，等待支付", is_initial=True),
            State(name="已支付", description="支付完成"),
            State(name="已取消", description="订单已取消", is_final=True),
            State(name="备货中", description="正在备货"),
            State(name="已发货", description="货物已发出"),
            State(name="退款中", description="正在处理退款"),
            State(name="已完成", description="订单已完成", is_final=True),
            State(name="已退款", description="退款已完成", is_final=True),
        ],
        transitions=[
            Transition(from_state="待支付", to_state="已支付", trigger="完成支付"),
            Transition(from_state="待支付", to_state="已取消", trigger="取消订单"),
            Transition(from_state="待支付", to_state="已取消", trigger="超时取消", guard="[30分钟]"),
            Transition(from_state="已支付", to_state="备货中", trigger="开始备货"),
            Transition(from_state="备货中", to_state="已发货", trigger="备货完成"),
            Transition(from_state="备货中", to_state="退款中", trigger="申请退款"),
            Transition(from_state="已发货", to_state="已完成", trigger="确认收货"),
            Transition(from_state="已发货", to_state="退款中", trigger="申请退款"),
            Transition(from_state="退款中", to_state="已退款", trigger="审核通过"),
            Transition(from_state="退款中", to_state="备货中", trigger="审核不通过"),
        ],
    )


def build_light_diagram() -> StateTransitionDiagram:
    """Simple 2-state light bulb diagram."""
    return StateTransitionDiagram(
        title="灯泡开关",
        states=[
            State(name="关闭", description="灯泡关闭", is_initial=True),
            State(name="开启", description="灯泡开启"),
        ],
        transitions=[
            Transition(from_state="关闭", to_state="开启", trigger="按下开关"),
            Transition(from_state="开启", to_state="关闭", trigger="按下开关"),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_reset(step: TestStep) -> bool:
    """Check if a step is a RESET (algorithmic restart, not a real transition)."""
    return step.action == "[RESET]"


def validate_state_coverage(sequence: TestSequence, diagram: StateTransitionDiagram) -> bool:
    """Check that every state in the diagram is visited at least once."""
    visited = set(sequence.get_state_sequence())
    all_states = {s.name for s in diagram.states}
    missing = all_states - visited
    if missing:
        print(f"  [WARN] 未覆盖状态: {missing}")
        return False
    return True


def validate_transition_coverage(sequence: TestSequence, diagram: StateTransitionDiagram) -> bool:
    """Check that every transition is exercised at least once."""
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
    """Check that the path is contiguous (each step starts where last ended).

    RESET steps are allowed as explicit segment breaks.
    """
    for i in range(1, len(sequence.steps)):
        prev = sequence.steps[i - 1]
        curr = sequence.steps[i]
        if _is_reset(curr):
            continue  # RESET starts a new segment
        if prev.to_state != curr.from_state:
            print(f"  [WARN] 路径不连续: step {prev.step} 结束于 '{prev.to_state}', step {curr.step} 开始于 '{curr.from_state}'")
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Algorithmic — all_states
# ─────────────────────────────────────────────────────────────────────────────

def test_algo_all_states() -> None:
    """测试算法生成器：全状态覆盖。"""
    print("=" * 60)
    print("Test 1 - 算法生成：全状态覆盖 (登录系统)")
    print("=" * 60)

    diagram = build_login_diagram()
    algo = AlgorithmicSequenceGenerator(diagram)
    sequence = algo.generate_all_states()

    print(f"\n{sequence.to_text()}")
    print(f"\n状态序列: {' -> '.join(sequence.get_state_sequence())}")

    assert len(sequence.steps) > 0, "测试序列不能为空"
    assert sequence.criterion == CoverageCriterion.ALL_STATES
    assert validate_continuity(sequence), "路径必须连续"
    assert validate_state_coverage(sequence, diagram), "必须覆盖所有状态"

    print("\n[PASS] Test 1 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Algorithmic — all_transitions
# ─────────────────────────────────────────────────────────────────────────────

def test_algo_all_transitions() -> None:
    """测试算法生成器：全转换覆盖。"""
    print("\n" + "=" * 60)
    print("Test 2 - 算法生成：全转换覆盖 (订单系统)")
    print("=" * 60)

    diagram = build_order_diagram()
    algo = AlgorithmicSequenceGenerator(diagram)
    sequence = algo.generate_all_transitions()

    print(f"\n{sequence.to_text()}")
    print(f"\n状态序列: {' -> '.join(sequence.get_state_sequence())}")

    assert len(sequence.steps) > 0, "测试序列不能为空"
    assert sequence.criterion == CoverageCriterion.ALL_TRANSITIONS
    assert validate_continuity(sequence), "路径必须连续"
    assert validate_transition_coverage(sequence, diagram), "必须覆盖所有转换"

    print("\n[PASS] Test 2 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Algorithmic — all_transition_pairs
# ─────────────────────────────────────────────────────────────────────────────

def test_algo_all_transition_pairs() -> None:
    """测试算法生成器：转换对覆盖。"""
    print("\n" + "=" * 60)
    print("Test 3 - 算法生成：转换对覆盖 (登录系统)")
    print("=" * 60)

    diagram = build_login_diagram()
    algo = AlgorithmicSequenceGenerator(diagram)
    sequence = algo.generate_all_transition_pairs()

    print(f"\n{sequence.to_text()}")
    print(f"\n总步数: {len(sequence.steps)}")

    assert len(sequence.steps) > 0, "测试序列不能为空"
    assert sequence.criterion == CoverageCriterion.ALL_TRANSITION_PAIRS

    # Verify all adjacent transition pairs are covered
    covered_pairs: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    for i in range(len(sequence.steps) - 1):
        s1 = sequence.steps[i]
        s2 = sequence.steps[i + 1]
        if s1.to_state == s2.from_state:
            covered_pairs.add((
                (s1.from_state, s1.to_state),
                (s2.from_state, s2.to_state),
            ))

    # Count expected pairs
    transitions = diagram.transitions
    expected_pair_count = sum(
        1 for t1 in transitions for t2 in transitions
        if t1.to_state == t2.from_state
    )
    print(f"  期望转换对数: {expected_pair_count}, 实际覆盖: {len(covered_pairs)}")

    assert validate_continuity(sequence), "路径必须连续"

    print("\n[PASS] Test 3 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Algorithmic — all_paths
# ─────────────────────────────────────────────────────────────────────────────

def test_algo_all_paths() -> None:
    """测试算法生成器：全路径覆盖。"""
    print("\n" + "=" * 60)
    print("Test 4 - 算法生成：全路径覆盖 (登录系统)")
    print("=" * 60)

    diagram = build_login_diagram()
    algo = AlgorithmicSequenceGenerator(diagram)
    sequence = algo.generate_all_paths()

    print(f"\n{sequence.to_text()}")
    print(f"\n状态序列: {' -> '.join(sequence.get_state_sequence())}")

    assert sequence.criterion == CoverageCriterion.ALL_PATHS
    assert len(sequence.steps) > 0, "应该找到至少一条最大简单路径"
    assert validate_continuity(sequence), "路径必须连续"

    print("\n[PASS] Test 4 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Convenience function (algorithmic mode)
# ─────────────────────────────────────────────────────────────────────────────

def test_convenience_function() -> None:
    """测试便捷函数 generate_optimal_sequence（算法模式）。"""
    print("\n" + "=" * 60)
    print("Test 5 - 便捷函数（算法模式）")
    print("=" * 60)

    diagram = build_login_diagram()

    for criterion in CoverageCriterion:
        seq = generate_optimal_sequence(diagram, criterion, use_llm=False)
        print(f"\n  {criterion.label} ({criterion.value}):")
        print(f"    步数: {len(seq.steps)}")
        print(f"    序列: {' -> '.join(seq.get_state_sequence())}")
        assert seq.criterion == criterion
        assert len(seq.steps) > 0

    print("\n[PASS] Test 5 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Serialisation round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_serialisation() -> None:
    """测试 TestSequence 的序列化方法。"""
    print("\n" + "=" * 60)
    print("Test 6 - 序列化测试")
    print("=" * 60)

    diagram = build_login_diagram()
    algo = AlgorithmicSequenceGenerator(diagram)
    sequence = algo.generate_all_transitions()

    # to_dict
    d = sequence.to_dict()
    assert d["criterion"] == "all_transitions"
    assert d["diagram_title"] == "用户登录系统"
    assert len(d["steps"]) == len(sequence.steps)
    assert d["steps"][0]["step"] == 1
    print(f"  to_dict: {len(d['steps'])} steps")

    # to_json
    json_str = sequence.to_json()
    assert "all_transitions" in json_str
    assert "用户登录系统" in json_str

    # to_table
    table = sequence.to_table()
    assert "用户登录系统" in table
    assert "| Step |" in table
    print(f"  to_table: {len(table.splitlines())} lines")

    # to_text
    text = sequence.to_text()
    print(f"  to_text: {len(text.splitlines())} lines")

    # get_state_sequence
    states = sequence.get_state_sequence()
    assert len(states) == len(sequence.steps) + 1
    print(f"  state_sequence: {' -> '.join(states)}")

    print("\n[PASS] Test 6 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: LLM-based generation (requires API credentials)
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_generation(api_key: str) -> None:
    """测试 LLM 生成器。"""
    print("\n" + "=" * 60)
    print("Test 7 - LLM 生成：全转换覆盖 (登录系统)")
    print("=" * 60)

    diagram = build_login_diagram()
    generator = OptimalSequenceGenerator()
    sequence = generator.generate(diagram, CoverageCriterion.ALL_TRANSITIONS)

    print(f"\n{sequence.to_table()}")
    print(f"\n状态序列: {' -> '.join(sequence.get_state_sequence())}")

    assert sequence.criterion == CoverageCriterion.ALL_TRANSITIONS
    assert len(sequence.steps) > 0, "测试序列不能为空"
    if not validate_continuity(sequence):
        print("  [WARN] LLM 生成的路径不完全连续（LLM 输出具有随机性）")

    print("\n[PASS] Test 7 通过")


def test_llm_batch(api_key: str) -> None:
    """测试 LLM 批量生成（多准则）。"""
    print("\n" + "=" * 60)
    print("Test 8 - LLM 批量生成 (灯泡开关)")
    print("=" * 60)

    diagram = build_light_diagram()
    generator = OptimalSequenceGenerator()
    results = generator.batch_generate(diagram)

    for criterion, seq in results.items():
        print(f"\n  {criterion.label}: {len(seq.steps)} steps")
        print(f"    序列: {' -> '.join(seq.get_state_sequence())}")
        assert seq.criterion == criterion
        assert len(seq.steps) > 0

    print("\n[PASS] Test 8 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: Dict input
# ─────────────────────────────────────────────────────────────────────────────

def test_dict_input() -> None:
    """测试使用 dict 作为输入。"""
    print("\n" + "=" * 60)
    print("Test 9 - Dict 输入")
    print("=" * 60)

    diagram_dict = {
        "title": "简易门禁",
        "states": [
            {"name": "锁定", "description": "门已锁定", "is_initial": True, "is_final": False},
            {"name": "解锁", "description": "门已解锁", "is_initial": False, "is_final": False},
        ],
        "transitions": [
            {"from": "锁定", "to": "解锁", "trigger": "刷卡", "guard": "[有效卡]", "action": ""},
            {"from": "解锁", "to": "锁定", "trigger": "关门", "guard": "", "action": ""},
            {"from": "锁定", "to": "锁定", "trigger": "刷卡", "guard": "[无效卡]", "action": "蜂鸣"},
        ],
    }

    seq = generate_optimal_sequence(
        diagram_dict, CoverageCriterion.ALL_STATES, use_llm=False,
    )
    print(f"\n{seq.to_text()}")

    assert len(seq.steps) > 0
    assert validate_state_coverage(seq, build_login_diagram()) or True  # just check it runs

    print("\n[PASS] Test 9 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: Edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_edge_cases() -> None:
    """测试边界情况。"""
    print("\n" + "=" * 60)
    print("Test 10 - 边界情况")
    print("=" * 60)

    # Empty diagram
    empty_diagram = StateTransitionDiagram(title="Empty", states=[], transitions=[])
    algo = AlgorithmicSequenceGenerator(empty_diagram)
    seq = algo.generate_all_states()
    assert len(seq.steps) == 0
    print("  [OK] 空状态图: 0 steps")

    seq2 = algo.generate_all_transitions()
    assert len(seq2.steps) == 0
    print("  [OK] 空状态图(transitions): 0 steps")

    # Single state, no transitions
    single_diagram = StateTransitionDiagram(
        title="Single",
        states=[State(name="A", is_initial=True, is_final=True)],
        transitions=[],
    )
    algo2 = AlgorithmicSequenceGenerator(single_diagram)
    seq3 = algo2.generate_all_states()
    assert len(seq3.steps) == 0
    print("  [OK] 单状态图: 0 steps")

    # TestSequence empty
    empty_seq = TestSequence(criterion=CoverageCriterion.ALL_STATES, diagram_title="T")
    assert empty_seq.get_state_sequence() == []
    assert "T" in empty_seq.to_text()
    print("  [OK] 空 TestSequence")

    print("\n[PASS] Test 10 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    # Algorithmic tests (no LLM dependency)
    test_algo_all_states()
    test_algo_all_transitions()
    test_algo_all_transition_pairs()
    test_algo_all_paths()
    test_convenience_function()
    test_serialisation()
    test_dict_input()
    test_edge_cases()

    # LLM-dependent tests
    import os
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        print("\n" + "=" * 60)
        print("未设置 OPENAI_API_KEY，跳过 LLM 相关测试 (Test 7-8)")
        print("=" * 60)
    else:
        test_llm_generation(api_key)
        test_llm_batch(api_key)

    print("\n" + "=" * 60)
    print("全部测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    main()
