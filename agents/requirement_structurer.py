"""
AutoTestDesign - RequirementStructurerAgent (FR1.1)
对解析后的需求进行深度结构化分析
"""

import json
from typing import List, Dict, Any

from utils.llm_client import get_shared_llm, call_llm_json
from prompts.templates import REQ_STRUCTURER_SYSTEM, REQ_STRUCTURER_USER
from graph.state import AutoTestState


def structure_requirements_batch(
    llm, requirements: List[Dict], batch_size: int = 5
) -> List[Dict]:
    """
    批量结构化需求（避免 token 超限）
    """
    structured = []

    for i in range(0, len(requirements), batch_size):
        batch = requirements[i: i + batch_size]
        try:
            result = call_llm_json(
                llm,
                REQ_STRUCTURER_SYSTEM,
                REQ_STRUCTURER_USER.format(
                    requirements_json=json.dumps(batch, ensure_ascii=False, indent=2)
                )
            )

            if isinstance(result, list):
                structured.extend(result)
            elif isinstance(result, dict):
                structured.append(result)

        except Exception as e:
            # 批次失败时，保留原始需求并补充空结构
            for req in batch:
                structured.append({
                    "req_id": req.get("req_id", "UNKNOWN"),
                    "title": req.get("title", ""),
                    "description": req.get("description", ""),
                    "input_fields": [],
                    "data_ranges": [],
                    "conditions": [],
                    "expected_actions": [req.get("description", "")],
                    "domain": "general",
                    "_parse_error": str(e),
                })

    return structured


def requirement_structurer_node(state: AutoTestState) -> Dict[str, Any]:
    """
    LangGraph 节点函数
    parsed_requirements → structured_requirements
    """
    parsed = state.get("parsed_requirements", [])
    progress = ["[ReqStructurer] 开始结构化需求分析..."]
    errors = []

    if not parsed:
        errors.append("[ReqStructurer] 没有可用的解析需求")
        return {
            "structured_requirements": [],
            "current_step": "error",
            "progress_messages": progress,
            "errors": errors,
        }

    try:
        llm = get_shared_llm()
        structured = structure_requirements_batch(llm, parsed)

        # 验证和补全输出
        validated = []
        for item in structured:
            validated.append({
                "req_id": item.get("req_id", "UNKNOWN"),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "input_fields": item.get("input_fields", []),
                "data_ranges": item.get("data_ranges", []),
                "conditions": item.get("conditions", []),
                "expected_actions": item.get("expected_actions", []),
                "domain": item.get("domain", "general"),
            })

        progress.append(
            f"[ReqStructurer] 结构化完成，共 {len(validated)} 条需求，"
            f"识别 {sum(len(r.get('input_fields', [])) for r in validated)} 个输入字段，"
            f"{sum(len(r.get('data_ranges', [])) for r in validated)} 个数据范围"
        )

        return {
            "structured_requirements": validated,
            "current_step": "structured",
            "completed_steps": state.get("completed_steps", []) + ["structure_reqs"],
            "progress_messages": progress,
            "errors": [],
        }

    except Exception as e:
        error_msg = f"[ReqStructurer] 结构化失败: {str(e)}"
        errors.append(error_msg)
        # Fallback：使用原始需求
        fallback = [
            {
                "req_id": r.get("req_id", f"REQ-{i+1:03d}"),
                "title": r.get("title", ""),
                "description": r.get("description", ""),
                "input_fields": [],
                "data_ranges": [],
                "conditions": [],
                "expected_actions": [r.get("description", "")],
                "domain": "general",
            }
            for i, r in enumerate(parsed)
        ]
        return {
            "structured_requirements": fallback,
            "current_step": "structured_fallback",
            "completed_steps": state.get("completed_steps", []) + ["structure_reqs"],
            "progress_messages": progress + [f"[ReqStructurer] 使用 Fallback 模式"],
            "errors": errors,
        }
