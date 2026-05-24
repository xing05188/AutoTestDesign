"""
ex4 — 状态转换图建模测试
基于 LLM 对需求文档进行状态转换图建模。
输入：需求文档（自然语言）
输出：状态转换图（JSON / Mermaid / 文本）
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "agents" / "whitebox"))

# Output directory for rendered images
OUTPUT_DIR = Path(__file__).resolve().parent / "diagrams"

from state_transition import (
    StateTransitionAnalyzer,
    StateTransitionDiagram,
    State,
    Transition,
    generate_state_transition_diagram,
)


# ─────────────────────────────────────────────────────────────────────────────
# Sample requirement documents for testing
# ─────────────────────────────────────────────────────────────────────────────

REQUIREMENT_LOGIN = """
用户登录系统需求：
1. 系统初始处于"未登录"状态。
2. 用户在登录页面输入用户名和密码，点击"登录"按钮后，系统进入"验证中"状态。
3. 如果验证成功（用户名和密码匹配），系统进入"已登录"状态。
4. 如果验证失败（用户名或密码错误），系统返回"未登录"状态，并显示错误提示。
5. 在"已登录"状态下，用户可以点击"退出登录"，系统返回"未登录"状态。
6. 在"已登录"状态下，如果用户超过30分钟无操作，系统自动进入"会话超时"状态。
7. 处于"会话超时"状态时，用户进行任何操作都会被重定向到登录页，系统返回"未登录"状态。
8. 在"已登录"状态下，用户可以查看个人信息、修改密码等操作，但状态保持为"已登录"。
"""

REQUIREMENT_ORDER = """
在线订单处理系统需求：
1. 用户创建订单后，订单处于"待支付"状态。
2. 用户在"待支付"状态下可以完成支付，订单进入"已支付"状态。
3. 用户在"待支付"状态下也可以取消订单，订单进入"已取消"状态（终止状态）。
4. 如果30分钟内未支付，"待支付"订单自动进入"已取消"状态。
5. 在"已支付"状态下，系统开始备货，订单进入"备货中"状态。
6. 备货完成后，订单进入"已发货"状态。
7. 在"已发货"状态下，用户确认收货后，订单进入"已完成"状态（终止状态）。
8. 在"备货中"或"已发货"状态下，用户可以申请退款，订单进入"退款中"状态。
9. 退款审核通过后，订单进入"已退款"状态（终止状态）。
10. 退款审核不通过，订单返回到原来的状态继续处理。
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _render_and_save(diagram: StateTransitionDiagram, name: str) -> str:
    """Render diagram to PNG and return the output path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = diagram.render(str(OUTPUT_DIR / f"{name}.png"))
    print(f"  [Image saved] {path}")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Programmatic construction (no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def test_programmatic() -> None:
    """测试手工构建状态转换图（不依赖 LLM）。"""
    print("=" * 60)
    print("Test 1 — 手工构建状态转换图")
    print("=" * 60)

    states = [
        State(name="Idle", description="等待用户操作", is_initial=True),
        State(name="Loading", description="加载数据中"),
        State(name="Success", description="加载成功"),
        State(name="Error", description="加载失败", is_final=True),
    ]

    transitions = [
        Transition(from_state="Idle", to_state="Loading", trigger="fetchData"),
        Transition(
            from_state="Loading", to_state="Success",
            trigger="onSuccess", guard="[response.ok]",
        ),
        Transition(
            from_state="Loading", to_state="Error",
            trigger="onError", guard="[response.error]",
            action="log error",
        ),
        Transition(
            from_state="Error", to_state="Idle",
            trigger="retry",
        ),
    ]

    diagram = StateTransitionDiagram(
        title="数据加载状态图",
        states=states,
        transitions=transitions,
    )

    print("\n--- JSON ---")
    print(diagram.to_json())
    print("\n--- Mermaid ---")
    print(diagram.to_mermaid())
    print("\n--- Text ---")
    print(diagram.to_text())

    # Basic assertions
    assert len(diagram.states) == 4
    assert len(diagram.transitions) == 4
    assert diagram.states[0].is_initial is True
    assert diagram.states[3].is_final is True

    d = diagram.to_dict()
    assert d["title"] == "数据加载状态图"
    assert len(d["states"]) == 4
    assert len(d["transitions"]) == 4

    _render_and_save(diagram, "test1_data_loading")

    print("\n[PASS] Test 1 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: LLM-based analysis (requires API credentials)
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_login(analyzer: StateTransitionAnalyzer) -> None:
    """测试从登录需求文档中提取状态转换图。"""
    print("\n" + "=" * 60)
    print("Test 2 — LLM 分析：用户登录系统")
    print("=" * 60)

    diagram = analyzer.analyze(REQUIREMENT_LOGIN)

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
    assert len(state_names) >= 3, f"预期至少3个状态，实际: {len(state_names)}"
    assert any(s.is_initial for s in diagram.states), "缺少初始状态"
    assert len(diagram.transitions) >= 3, f"预期至少3个转换，实际: {len(diagram.transitions)}"

    for t in diagram.transitions:
        assert t.from_state in state_names, f"转换来源 '{t.from_state}' 不在状态列表中"
        assert t.to_state in state_names, f"转换目标 '{t.to_state}' 不在状态列表中"
        assert t.trigger, f"转换 {t.from_state}->{t.to_state} 缺少触发器"

    _render_and_save(diagram, "test2_login_system")

    print("\n[PASS] Test 2 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: LLM-based analysis for order system
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_order(analyzer: StateTransitionAnalyzer) -> None:
    """测试从订单系统需求文档中提取状态转换图。"""
    print("\n" + "=" * 60)
    print("Test 3 — LLM 分析：在线订单处理系统")
    print("=" * 60)

    diagram = analyzer.analyze(REQUIREMENT_ORDER)

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
    assert len(state_names) >= 5, f"预期至少5个状态，实际: {len(state_names)}"
    assert any(s.is_initial for s in diagram.states), "缺少初始状态"
    assert any(s.is_final for s in diagram.states), "缺少终止状态"
    assert len(diagram.transitions) >= 5, f"预期至少5个转换，实际: {len(diagram.transitions)}"

    for t in diagram.transitions:
        assert t.from_state in state_names, f"转换来源 '{t.from_state}' 不在状态列表中"
        assert t.to_state in state_names, f"转换目标 '{t.to_state}' 不在状态列表中"
        assert t.trigger, f"转换 {t.from_state}->{t.to_state} 缺少触发器"

    _render_and_save(diagram, "test3_order_system")

    print("\n[PASS] Test 3 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Convenience function
# ─────────────────────────────────────────────────────────────────────────────

def test_convenience_function() -> None:
    """测试便捷函数 generate_state_transition_diagram。"""
    print("\n" + "=" * 60)
    print("Test 4 — 便捷函数")
    print("=" * 60)

    diagram = generate_state_transition_diagram(
        requirements="一个简单的灯泡：初始为'关闭'状态，按下开关进入'开启'状态，"
                     "再按一次开关回到'关闭'状态。",
    )

    print(f"\n状态数: {len(diagram.states)}")
    print(f"转换数: {len(diagram.transitions)}")
    print("\n--- Mermaid ---")
    print(diagram.to_mermaid())

    assert len(diagram.states) >= 2
    assert len(diagram.transitions) >= 2

    _render_and_save(diagram, "test4_light_bulb")

    print("\n[PASS] Test 4 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Dict round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_dict_roundtrip() -> None:
    """测试 to_dict 数据完整性。"""
    print("\n" + "=" * 60)
    print("Test 5 — Dict 数据完整性")
    print("=" * 60)

    states = [
        State(name="A", description="起始", is_initial=True,
              entry_actions=["init"], exit_actions=["cleanup"]),
        State(name="B", description="中间"),
        State(name="C", description="结束", is_final=True),
    ]
    transitions = [
        Transition(from_state="A", to_state="B", trigger="go", guard="[ok]", action="move"),
        Transition(from_state="B", to_state="C", trigger="finish"),
    ]
    diagram = StateTransitionDiagram(title="Test", states=states, transitions=transitions)

    d = diagram.to_dict()
    assert d["title"] == "Test"
    assert len(d["states"]) == 3
    assert d["states"][0]["name"] == "A"
    assert d["states"][0]["is_initial"] is True
    assert d["states"][0]["entry_actions"] == ["init"]
    assert d["states"][0]["exit_actions"] == ["cleanup"]
    assert d["states"][2]["is_final"] is True
    assert len(d["transitions"]) == 2
    assert d["transitions"][0]["guard"] == "[ok]"
    assert d["transitions"][0]["action"] == "move"

    print("[PASS] Test 5 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Multi-format rendering (no LLM dependency)
# ─────────────────────────────────────────────────────────────────────────────

def test_multi_format_render() -> None:
    """测试多种格式的图像渲染。"""
    print("\n" + "=" * 60)
    print("Test 6 — 多格式渲染 (PNG / SVG / PDF)")
    print("=" * 60)

    states = [
        State(name="Off", description="关机", is_initial=True),
        State(name="On", description="运行中"),
        State(name="Sleep", description="休眠"),
    ]
    transitions = [
        Transition(from_state="Off", to_state="On", trigger="pressPower"),
        Transition(from_state="On", to_state="Sleep", trigger="timeout", guard="[5min idle]"),
        Transition(from_state="Sleep", to_state="On", trigger="pressKey"),
        Transition(from_state="On", to_state="Off", trigger="pressPower", guard="[hold 3s]"),
        Transition(from_state="Sleep", to_state="Off", trigger="pressPower", guard="[hold 5s]"),
    ]
    diagram = StateTransitionDiagram(title="Power State", states=states, transitions=transitions)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for fmt in ("png", "svg", "pdf"):
        path = diagram.render(str(OUTPUT_DIR / f"test6_power_state.{fmt}"), format=fmt)
        assert Path(path).exists(), f"{fmt} 文件未生成: {path}"
        size_kb = Path(path).stat().st_size / 1024
        print(f"  [{fmt.upper()}] {path} ({size_kb:.1f} KB)")

    print("[PASS] Test 6 通过")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    # Test 1: always runs (no LLM dependency)
    test_programmatic()

    # Test 5: dict round-trip (no LLM dependency)
    test_dict_roundtrip()

    # Test 6: multi-format rendering (no LLM dependency)
    test_multi_format_render()

    # LLM-dependent tests (only if credentials are available)
    import os
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        print("\n" + "=" * 60)
        print("未设置 OPENAI_API_KEY，跳过 LLM 相关测试 (Test 2-4)")
        print("=" * 60)
        print(f"\n所有生成的图像文件位于: {OUTPUT_DIR}")
        return

    analyzer = StateTransitionAnalyzer()

    test_llm_login(analyzer)
    test_llm_order(analyzer)
    test_convenience_function()

    print("\n" + "=" * 60)
    print("全部测试通过!")
    print(f"所有生成的图像文件位于: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
