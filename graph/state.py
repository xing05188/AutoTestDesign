"""
AutoTestDesign - LangGraph 共享状态定义
贯穿整个多智能体工作流的状态容器
"""

from typing import List, Dict, Any, Optional, Annotated
from typing_extensions import TypedDict
import operator

from models.schemas import (
    Requirement, RiskItem, TestCase,
    StateTransitionModel, ExportArtifact, OptimizationResult
)


class AutoTestState(TypedDict):
    """
    LangGraph 共享状态
    所有智能体节点读写同一个状态对象
    """

    # ── 输入 ────────────────────────────────────────────────────────
    raw_input: str                              # 原始需求文本
    input_format: str                           # "csv" | "text" | "manual"
    config: Dict[str, Any]                      # 用户配置（优先级阈值等）

    # ── FR1.0 / FR1.1 解析结果 ────────────────────────────────────
    parsed_requirements: List[Dict]             # RawRequirement 列表（dict 格式）
    structured_requirements: List[Dict]         # Requirement 列表（dict 格式）

    # ── FR2.0 风险分析 ─────────────────────────────────────────────
    risk_analysis: List[Dict]                   # RiskItem 列表

    # ── FR3.0 黑盒测试用例 ─────────────────────────────────────────
    blackbox_tests: List[Dict]                  # TestCase 列表（黑盒）

    # ── FR4.0 白盒测试用例 ─────────────────────────────────────────
    whitebox_tests: List[Dict]                  # TestCase 列表（白盒）
    state_models: List[Dict]                    # StateTransitionModel 列表
    state_diagrams: Dict[str, str]              # req_id → DOT 图形字符串

    # ── FR5.0 Oracle 增强 ──────────────────────────────────────────
    enriched_tests: List[Dict]                  # 含 Oracle 的测试用例

    # ── FR7.0 优化结果 ─────────────────────────────────────────────
    optimized_suite: List[Dict]                 # 优化后的最终测试套件
    optimization_result: Dict                   # OptimizationResult

    # ── FR6.0 导出产物 ─────────────────────────────────────────────
    export_artifact: Dict                       # ExportArtifact

    # ── 工作流控制 ────────────────────────────────────────────────
    current_step: str
    completed_steps: List[str]
    errors: Annotated[List[str], operator.add]  # 错误列表（支持并行节点追加）
    progress_messages: Annotated[List[str], operator.add]  # 进度消息


def create_initial_state(
    raw_input: str,
    input_format: str = "text",
    config: Optional[Dict] = None
) -> AutoTestState:
    """创建初始状态"""
    return AutoTestState(
        raw_input=raw_input,
        input_format=input_format,
        config=config or {
            "risk_threshold_high": 7.0,
            "risk_threshold_medium": 4.0,
            "min_coverage_rate": 0.8,
            "max_test_cases": 100,
            "enable_bva": True,
            "enable_ep": True,
            "enable_decision_table": True,
            "enable_state_transition": True,
        },
        parsed_requirements=[],
        structured_requirements=[],
        risk_analysis=[],
        blackbox_tests=[],
        whitebox_tests=[],
        state_models=[],
        state_diagrams={},
        enriched_tests=[],
        optimized_suite=[],
        optimization_result={},
        export_artifact={},
        current_step="init",
        completed_steps=[],
        errors=[],
        progress_messages=[],
    )
