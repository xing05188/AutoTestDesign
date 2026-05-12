"""
AutoTestDesign - WhiteBoxTestAgent (FR4.0)
建模系统状态行为，生成最优测试序列
技术：State Transition Testing (ISO/IEC/IEEE 29119-4 Section 5.4)
"""

import json
from typing import List, Dict, Any

from utils.llm_client import get_shared_llm, call_llm_json
from prompts.templates import STATE_TRANSITION_SYSTEM, STATE_TRANSITION_USER
from graph.state import AutoTestState


def get_risk_priority(req_id: str, risk_analysis: List[Dict]) -> str:
    for risk in risk_analysis:
        if risk.get("req_id") == req_id:
            return risk.get("priority", "Medium")
    return "Medium"


def has_state_behavior(req: Dict) -> bool:
    """
    判断需求是否适合状态转换建模
    有条件流转、多步骤流程、状态相关词汇
    """
    desc = (req.get("description", "") + " " + " ".join(req.get("conditions", []))).lower()
    state_keywords = [
        "状态", "转换", "登录", "退出", "流程", "步骤", "锁定", "激活", "禁用",
        "待", "进行中", "完成", "取消", "审批", "提交", "重置", "验证",
        "state", "transition", "flow", "process", "login", "logout", "lock",
        "active", "inactive", "pending", "approved", "rejected", "expired"
    ]
    return any(kw in desc for kw in state_keywords)


def generate_state_model(llm, req: Dict, priority: str) -> Dict:
    """生成单条需求的状态转换模型"""
    try:
        result = call_llm_json(
            llm,
            STATE_TRANSITION_SYSTEM,
            STATE_TRANSITION_USER.format(
                requirement_json=json.dumps(req, ensure_ascii=False, indent=2),
                priority=priority,
            )
        )

        # 确保是字典格式
        if isinstance(result, list) and len(result) > 0:
            result = result[0]

        if not isinstance(result, dict):
            raise ValueError("返回格式不正确")

        return result

    except Exception as e:
        # Fallback：生成简单的两状态模型
        req_id = req.get("req_id", "REQ")
        return {
            "req_id": req_id,
            "states": [
                {"state_id": "S0", "name": "初始状态", "description": "系统初始状态", "is_initial": True, "is_final": False},
                {"state_id": "S1", "name": "处理中", "description": "处理中状态", "is_initial": False, "is_final": False},
                {"state_id": "S2", "name": "完成状态", "description": "操作完成", "is_initial": False, "is_final": True},
            ],
            "transitions": [
                {"from_state": "S0", "event": "触发操作", "condition": req.get("conditions", [""])[0] if req.get("conditions") else "", "to_state": "S1", "action": "开始处理"},
                {"from_state": "S1", "event": "处理完成", "condition": "", "to_state": "S2", "action": "返回结果"},
            ],
            "test_sequences": [
                {
                    "tc_id": f"TC-{req_id}-ST-001",
                    "req_id": req_id,
                    "technique": "State_Transition",
                    "title": f"状态转换基本路径测试",
                    "description": f"覆盖完整状态序列：S0→S1→S2",
                    "preconditions": ["系统处于初始状态"],
                    "test_steps": [
                        {"step_number": 1, "action": "触发操作", "expected": "系统进入处理中状态"},
                        {"step_number": 2, "action": "等待处理完成", "expected": "系统显示完成状态"},
                    ],
                    "test_data": {},
                    "expected_result": "系统成功完成状态转换，最终显示完成状态",
                    "priority": priority,
                    "is_positive": True,
                    "coverage_tags": ["S0", "S1", "S2"],
                }
            ],
            "dot_graph": f'digraph G {{\n  rankdir=LR;\n  S0 [label="初始状态" shape=circle style=filled fillcolor=lightblue];\n  S1 [label="处理中" shape=circle];\n  S2 [label="完成" shape=doublecircle];\n  S0 -> S1 [label="触发操作"];\n  S1 -> S2 [label="处理完成"];\n}}',
            "_fallback": True,
            "_error": str(e),
        }


def normalize_st_test_case(tc: Dict, req_id: str) -> Dict:
    """规范化状态转换测试用例"""
    return {
        "tc_id": tc.get("tc_id", f"TC-{req_id}-ST-ERR"),
        "req_id": tc.get("req_id", req_id),
        "technique": "State_Transition",
        "title": tc.get("title", "状态转换测试"),
        "description": tc.get("description", ""),
        "preconditions": tc.get("preconditions", []),
        "test_steps": tc.get("test_steps", []),
        "test_data": tc.get("test_data", {}),
        "expected_result": tc.get("expected_result", ""),
        "priority": tc.get("priority", "Medium"),
        "is_positive": tc.get("is_positive", True),
        "coverage_tags": tc.get("coverage_tags", []),
    }


def whitebox_tester_node(state: AutoTestState) -> Dict[str, Any]:
    """
    LangGraph 节点函数（可与 blackbox 并行执行）
    structured_requirements + risk_analysis → whitebox_tests + state_models + state_diagrams
    """
    structured = state.get("structured_requirements", [])
    risk_analysis = state.get("risk_analysis", [])
    config = state.get("config", {})

    enable_st = config.get("enable_state_transition", True)

    progress = ["[WhiteBox] 开始生成白盒测试用例..."]
    errors = []

    if not structured or not enable_st:
        return {
            "whitebox_tests": [],
            "state_models": [],
            "state_diagrams": {},
            "current_step": "whitebox_done",
            "progress_messages": progress + ["[WhiteBox] 跳过（未启用或无需求）"],
            "errors": [],
        }

    llm = get_shared_llm()
    all_tests = []
    state_models = []
    state_diagrams = {}

    for req in structured:
        req_id = req.get("req_id", "UNKNOWN")
        priority = get_risk_priority(req_id, risk_analysis)

        # 判断是否适合状态转换建模
        if not has_state_behavior(req):
            progress.append(f"[WhiteBox] {req_id}: 跳过（无状态行为特征）")
            continue

        progress.append(f"[WhiteBox] {req_id}: 生成状态转换模型...")

        model = generate_state_model(llm, req, priority)

        # 提取测试序列
        test_sequences = model.get("test_sequences", [])
        normalized = [normalize_st_test_case(tc, req_id) for tc in test_sequences]
        all_tests.extend(normalized)

        # 保存状态模型（去掉 test_sequences 避免重复）
        model_data = {k: v for k, v in model.items() if k != "test_sequences"}
        state_models.append(model_data)

        # 保存 DOT 图形
        dot_graph = model.get("dot_graph", "")
        if dot_graph:
            state_diagrams[req_id] = dot_graph

        progress.append(
            f"[WhiteBox] {req_id}: 状态数={len(model.get('states', []))}, "
            f"转换数={len(model.get('transitions', []))}, "
            f"测试序列={len(normalized)}"
        )

    progress.append(f"[WhiteBox] 白盒测试用例生成完成，共 {len(all_tests)} 个")

    return {
        "whitebox_tests": all_tests,
        "state_models": state_models,
        "state_diagrams": state_diagrams,
        "current_step": "whitebox_done",
        "completed_steps": state.get("completed_steps", []) + ["generate_whitebox"],
        "progress_messages": progress,
        "errors": errors,
    }
