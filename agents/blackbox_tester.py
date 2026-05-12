"""
AutoTestDesign - BlackBoxTestAgent (FR3.0)
自动应用三种黑盒测试技术生成测试用例：
- 等价类划分 (EP)
- 边界值分析 (BVA)
- 决策表 (Decision Table)
"""

import json
from typing import List, Dict, Any

from utils.llm_client import get_shared_llm, call_llm_json
from prompts.templates import (
    BLACKBOX_SYSTEM, BLACKBOX_USER,
)
from graph.state import AutoTestState


def get_risk_priority(req_id: str, risk_analysis: List[Dict]) -> str:
    """获取需求的风险优先级"""
    for risk in risk_analysis:
        if risk.get("req_id") == req_id:
            return risk.get("priority", "Medium")
    return "Medium"


def generate_blackbox_tests(llm, structured: List[Dict], risk_analysis: List[Dict]) -> List[Dict]:
    """一次性生成全部黑盒测试用例"""
    result = call_llm_json(
        llm,
        BLACKBOX_SYSTEM,
        BLACKBOX_USER.format(
            structured_requirements_json=json.dumps(structured, ensure_ascii=False, indent=2),
            risk_analysis_json=json.dumps(risk_analysis, ensure_ascii=False, indent=2),
        ),
    )

    if isinstance(result, dict):
        for key in ("blackbox_tests", "test_cases", "tests"):
            if key in result and isinstance(result[key], list):
                return result[key]
        return [result]
    if isinstance(result, list):
        return result
    return [result] if result else []



def normalize_test_case(tc: Dict, req_id: str) -> Dict:
    """规范化测试用例结构"""
    return {
        "tc_id": tc.get("tc_id", f"TC-{req_id}-UNKNOWN"),
        "req_id": tc.get("req_id", req_id),
        "technique": tc.get("technique", "Equivalence_Partitioning"),
        "title": tc.get("title", "未命名测试用例"),
        "description": tc.get("description", ""),
        "preconditions": tc.get("preconditions", []),
        "test_steps": tc.get("test_steps", []),
        "test_data": tc.get("test_data", {}),
        "expected_result": tc.get("expected_result", ""),
        "priority": tc.get("priority", "Medium"),
        "is_positive": tc.get("is_positive", True),
        "coverage_tags": tc.get("coverage_tags", []),
        "decision_rule": tc.get("decision_rule", {}),
    }


def blackbox_tester_node(state: AutoTestState) -> Dict[str, Any]:
    """
    LangGraph 节点函数（可与 whitebox 并行执行）
    structured_requirements + risk_analysis → blackbox_tests
    """
    structured = state.get("structured_requirements", [])
    risk_analysis = state.get("risk_analysis", [])
    config = state.get("config", {})

    enable_ep = config.get("enable_ep", True)
    enable_bva = config.get("enable_bva", True)
    enable_dt = config.get("enable_decision_table", True)

    progress = ["[BlackBox] 开始生成黑盒测试用例..."]
    errors = []

    if not structured:
        return {
            "blackbox_tests": [],
            "current_step": "blackbox_done",
            "progress_messages": progress,
            "errors": ["[BlackBox] 无可用需求"],
        }

    llm = get_shared_llm()
    all_tests = []

    try:
        raw_tests = generate_blackbox_tests(llm, structured, risk_analysis)
        all_tests = [normalize_test_case(tc, tc.get("req_id", "UNKNOWN")) for tc in raw_tests]

        technique_counts: Dict[str, int] = {}
        req_counts: Dict[str, int] = {}
        for test_case in all_tests:
            req_id = test_case.get("req_id", "UNKNOWN")
            technique = test_case.get("technique", "Unknown")
            req_counts[req_id] = req_counts.get(req_id, 0) + 1
            technique_counts[technique] = technique_counts.get(technique, 0) + 1

        progress.append(f"[BlackBox] 单次生成完成，共 {len(all_tests)} 个测试用例")
        progress.append(
            "[BlackBox] 技术分布: " + ", ".join(f"{k}={v}" for k, v in sorted(technique_counts.items()))
        )
        progress.append(
            "[BlackBox] 需求覆盖: " + ", ".join(f"{k}={v}" for k, v in sorted(req_counts.items()))
        )

    except Exception as e:
        errors.append(f"[BlackBox] 单次黑盒生成失败: {str(e)}")

        # 失败时保留一个极简本地回退，避免整个工作流中断
        for req in structured:
            req_id = req.get("req_id", "UNKNOWN")
            all_tests.append({
                "tc_id": f"TC-{req_id}-FB-001",
                "req_id": req_id,
                "technique": "Equivalence_Partitioning",
                "title": f"{req.get('title', '')}-回退用例",
                "description": "LLM 黑盒生成失败时的本地回退用例",
                "preconditions": [],
                "test_steps": [{"step_number": 1, "action": "执行基本正向流程", "expected": "系统正常响应"}],
                "test_data": {},
                "expected_result": "系统应正常处理该需求的基本场景",
                "priority": get_risk_priority(req_id, risk_analysis),
                "is_positive": True,
                "coverage_tags": ["fallback"],
                "decision_rule": {},
            })
        progress.append(f"[BlackBox] 回退生成完成，共 {len(all_tests)} 个测试用例")

    progress.append(f"[BlackBox] 黑盒测试用例生成完成，共 {len(all_tests)} 个")

    return {
        "blackbox_tests": all_tests,
        "current_step": "blackbox_done",
        "completed_steps": state.get("completed_steps", []) + ["generate_blackbox"],
        "progress_messages": progress,
        "errors": errors,
    }
