"""
AutoTestDesign - TestOracleAgent (FR5.0)
为每个测试用例合成精确的预期结果（Test Oracle）
"""

import json
from typing import List, Dict, Any

from utils.llm_client import get_shared_llm, call_llm_json
from prompts.templates import ORACLE_SYSTEM, ORACLE_USER
from graph.state import AutoTestState


def build_req_description_map(structured_reqs: List[Dict]) -> Dict[str, str]:
    """构建需求 ID → 描述的映射"""
    return {
        r.get("req_id", ""): (
            f"{r.get('title', '')}: {r.get('description', '')}\n"
            f"条件: {'; '.join(r.get('conditions', []))}\n"
            f"预期行为: {'; '.join(r.get('expected_actions', []))}"
        )
        for r in structured_reqs
    }


def enrich_oracle_batch(
    llm,
    test_cases: List[Dict],
    req_desc_map: Dict[str, str],
    batch_size: int = 10
) -> List[Dict]:
    """批量为测试用例添加精确 Oracle"""
    enriched = []

    for i in range(0, len(test_cases), batch_size):
        batch = test_cases[i: i + batch_size]

        # 收集本批次相关的需求描述
        batch_req_ids = set(tc.get("req_id", "") for tc in batch)
        relevant_descs = {
            req_id: desc
            for req_id, desc in req_desc_map.items()
            if req_id in batch_req_ids
        }

        try:
            result = call_llm_json(
                llm,
                ORACLE_SYSTEM,
                ORACLE_USER.format(
                    requirement_descriptions=json.dumps(
                        relevant_descs, ensure_ascii=False, indent=2
                    ),
                    test_cases_json=json.dumps(batch, ensure_ascii=False, indent=2),
                )
            )

            if isinstance(result, list):
                enriched.extend(result)
            elif isinstance(result, dict) and "test_cases" in result:
                enriched.extend(result["test_cases"])
            else:
                # 如果 LLM 返回单个对象，则 fallback 到原始批次
                enriched.extend(batch)

        except Exception as e:
            # Oracle 生成失败时保留原始测试用例
            enriched.extend(batch)

    return enriched


def oracle_generator_node(state: AutoTestState) -> Dict[str, Any]:
    """
    LangGraph 节点函数
    blackbox_tests + whitebox_tests → enriched_tests
    """
    blackbox = state.get("blackbox_tests", [])
    whitebox = state.get("whitebox_tests", [])
    structured = state.get("structured_requirements", [])

    all_tests = blackbox + whitebox
    progress = [f"[Oracle] 开始为 {len(all_tests)} 个测试用例合成预期结果..."]
    errors = []

    if not all_tests:
        return {
            "enriched_tests": [],
            "current_step": "oracle_done",
            "progress_messages": progress,
            "errors": ["[Oracle] 没有可用的测试用例"],
        }

    try:
        llm = get_shared_llm()
        req_desc_map = build_req_description_map(structured)

        enriched = enrich_oracle_batch(llm, all_tests, req_desc_map)

        progress.append(f"[Oracle] Oracle 合成完成，{len(enriched)} 个测试用例已增强")

        return {
            "enriched_tests": enriched,
            "current_step": "oracle_done",
            "completed_steps": state.get("completed_steps", []) + ["generate_oracle"],
            "progress_messages": progress,
            "errors": [],
        }

    except Exception as e:
        error_msg = f"[Oracle] Oracle 生成失败: {str(e)}"
        errors.append(error_msg)

        return {
            "enriched_tests": all_tests,  # Fallback 使用原始测试用例
            "current_step": "oracle_done_fallback",
            "completed_steps": state.get("completed_steps", []) + ["generate_oracle"],
            "progress_messages": progress + ["[Oracle] 使用原始预期结果（未增强）"],
            "errors": errors,
        }
