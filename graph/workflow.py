"""
AutoTestDesign - LangGraph 工作流构建
将所有智能体节点编排为有向状态图
"""

from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END

from graph.state import AutoTestState
from agents.input_parser import input_parser_node
from agents.requirement_structurer import requirement_structurer_node
from agents.risk_analyzer import risk_analyzer_node
from agents.blackbox_tester import blackbox_tester_node
from agents.whitebox_tester import whitebox_tester_node
from agents.oracle_generator import oracle_generator_node
from agents.optimizer import optimizer_node
from agents.exporter import exporter_node


# ─────────────────────────────────────────────
# 条件路由函数
# ─────────────────────────────────────────────

def route_after_parsing(state: AutoTestState) -> Literal["continue", "error"]:
    """解析后的路由：有需求则继续，否则终止"""
    if state.get("parsed_requirements") and len(state["parsed_requirements"]) > 0:
        return "continue"
    return "error"


def route_after_structuring(state: AutoTestState) -> Literal["continue", "error"]:
    """结构化后的路由"""
    if state.get("structured_requirements") and len(state["structured_requirements"]) > 0:
        return "continue"
    return "error"


# ─────────────────────────────────────────────
# 并行节点：等待 blackbox + whitebox 完成后汇合
# ─────────────────────────────────────────────

def merge_test_results_node(state: AutoTestState) -> Dict[str, Any]:
    """
    汇合节点：等待黑盒和白盒测试用例都生成后继续
    由于 LangGraph 的并行节点会自动合并状态，此节点只需记录进度
    """
    bb_count = len(state.get("blackbox_tests", []))
    wb_count = len(state.get("whitebox_tests", []))

    return {
        "current_step": "tests_merged",
        "progress_messages": [
            f"[Merge] 测试用例汇合完成：黑盒 {bb_count} 个，白盒 {wb_count} 个，合计 {bb_count + wb_count} 个"
        ],
        "errors": [],
    }


# ─────────────────────────────────────────────
# 构建工作流图
# ─────────────────────────────────────────────

def build_workflow() -> StateGraph:
    """
    构建 LangGraph 多智能体工作流

    工作流结构：
    input_parser
        ↓ (条件路由)
    req_structurer
        ↓ (条件路由)
    risk_analyzer
        ↓ (并行分叉)
    blackbox_tester  whitebox_tester
        ↘              ↙
           merge_node
              ↓
         oracle_generator
              ↓
          optimizer
              ↓
           exporter
              ↓
             END
    """
    builder = StateGraph(AutoTestState)

    # ── 注册节点 ────────────────────────────────
    builder.add_node("parse_input",       input_parser_node)
    builder.add_node("structure_reqs",    requirement_structurer_node)
    builder.add_node("analyze_risk",      risk_analyzer_node)
    builder.add_node("generate_blackbox", blackbox_tester_node)
    builder.add_node("generate_whitebox", whitebox_tester_node)
    builder.add_node("merge_tests",       merge_test_results_node)
    builder.add_node("generate_oracle",   oracle_generator_node)
    builder.add_node("optimize_suite",    optimizer_node)
    builder.add_node("export_artifacts",  exporter_node)

    # ── 设置入口节点 ────────────────────────────
    builder.set_entry_point("parse_input")

    # ── 添加边 ──────────────────────────────────

    # 条件路由：解析后检查是否有需求
    builder.add_conditional_edges(
        "parse_input",
        route_after_parsing,
        {
            "continue": "structure_reqs",
            "error": END,
        }
    )

    # 条件路由：结构化后检查
    builder.add_conditional_edges(
        "structure_reqs",
        route_after_structuring,
        {
            "continue": "analyze_risk",
            "error": END,
        }
    )

    # 风险分析完成后并行分叉到黑盒和白盒
    builder.add_edge("analyze_risk",      "generate_blackbox")
    builder.add_edge("analyze_risk",      "generate_whitebox")

    # 黑盒和白盒完成后汇合
    builder.add_edge("generate_blackbox", "merge_tests")
    builder.add_edge("generate_whitebox", "merge_tests")

    # 后续顺序流程
    builder.add_edge("merge_tests",       "generate_oracle")
    builder.add_edge("generate_oracle",   "optimize_suite")
    builder.add_edge("optimize_suite",    "export_artifacts")
    builder.add_edge("export_artifacts",  END)

    return builder


def compile_workflow():
    """编译工作流，返回可执行的图"""
    builder = build_workflow()
    return builder.compile()


# 全局编译好的工作流实例
_compiled_graph = None


def get_compiled_graph():
    """获取编译好的工作流（单例模式）"""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_workflow()
    return _compiled_graph
