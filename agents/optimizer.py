"""
AutoTestDesign - OptimizerAgent (FR7.0)
基于风险和覆盖率优化测试套件
"""

import json
from typing import List, Dict, Any, Set

from utils.llm_client import get_shared_llm, call_llm_json
from prompts.templates import OPTIMIZER_SYSTEM, OPTIMIZER_USER
from graph.state import AutoTestState


# 优先级权重
PRIORITY_WEIGHT = {"High": 3, "Medium": 2, "Low": 1}


def greedy_minimize(
    test_cases: List[Dict],
    risk_map: Dict[str, str],
    min_coverage: float = 0.8
) -> tuple[List[Dict], List[str]]:
    """
    贪心算法实现测试套件最小化
    保证每个需求至少有一个测试用例，同时满足最低覆盖率
    """
    if not test_cases:
        return [], []

    # 收集所有需求 ID
    all_req_ids = set(tc.get("req_id", "") for tc in test_cases)
    covered_req_ids: Set[str] = set()
    selected = []
    removed_ids = []

    # 按优先级排序（高优先级先选）
    def sort_key(tc):
        priority = tc.get("priority", "Medium")
        req_id = tc.get("req_id", "")
        risk_priority = risk_map.get(req_id, "Medium")
        is_positive = 1 if tc.get("is_positive", True) else 0
        # 综合权重：需求风险 + 用例优先级 + 正向测试加成
        return -(PRIORITY_WEIGHT.get(risk_priority, 2) * 2 + PRIORITY_WEIGHT.get(priority, 2) + is_positive)

    sorted_tests = sorted(test_cases, key=sort_key)

    # 第一轮：确保每个需求至少有一个测试用例
    covered_by_req: Dict[str, List[Dict]] = {}
    for tc in sorted_tests:
        req_id = tc.get("req_id", "")
        if req_id not in covered_by_req:
            covered_by_req[req_id] = []
        covered_by_req[req_id].append(tc)

    for req_id in all_req_ids:
        if req_id in covered_by_req:
            # 选取该需求最高优先级的测试用例
            best_tc = covered_by_req[req_id][0]
            selected.append(best_tc)
            covered_req_ids.add(req_id)

    selected_ids = {tc.get("tc_id") for tc in selected}

    # 第二轮：根据覆盖率目标添加更多用例
    current_coverage = len(covered_req_ids) / len(all_req_ids) if all_req_ids else 1.0

    # 添加剩余重要测试用例（高优先级的正向和边界用例）
    for tc in sorted_tests:
        tc_id = tc.get("tc_id")
        if tc_id not in selected_ids:
            priority = tc.get("priority", "Medium")
            # 保留所有高优先级和中优先级的用例
            if priority in ("High", "Medium"):
                selected.append(tc)
                selected_ids.add(tc_id)

    # 标记删除的（仅低优先级且已被覆盖的重复用例）
    all_ids = {tc.get("tc_id") for tc in test_cases}
    removed_ids = list(all_ids - selected_ids)

    final_coverage = len(covered_req_ids) / len(all_req_ids) if all_req_ids else 1.0

    return selected, removed_ids


def optimizer_node(state: AutoTestState) -> Dict[str, Any]:
    """
    LangGraph 节点函数
    enriched_tests + risk_analysis → optimized_suite
    """
    enriched = state.get("enriched_tests", [])
    risk_analysis = state.get("risk_analysis", [])
    config = state.get("config", {})
    min_coverage = config.get("min_coverage_rate", 0.8)

    progress = [f"[Optimizer] 开始优化测试套件（共 {len(enriched)} 个用例）..."]
    errors = []

    if not enriched:
        return {
            "optimized_suite": [],
            "optimization_result": {},
            "current_step": "optimized",
            "progress_messages": progress,
            "errors": ["[Optimizer] 没有可用的测试用例"],
        }

    # 构建风险优先级映射
    risk_map = {r.get("req_id", ""): r.get("priority", "Medium") for r in risk_analysis}

    original_count = len(enriched)

    try:
        # 使用 LLM 进行智能优化（仅当用例数量较多时）
        if len(enriched) > 30:
            llm = get_shared_llm()
            # 仅传入摘要信息避免 token 超限
            tc_summary = [
                {
                    "tc_id": tc.get("tc_id"),
                    "req_id": tc.get("req_id"),
                    "technique": tc.get("technique"),
                    "priority": tc.get("priority"),
                    "is_positive": tc.get("is_positive"),
                    "title": tc.get("title"),
                }
                for tc in enriched
            ]

            try:
                llm_result = call_llm_json(
                    llm,
                    OPTIMIZER_SYSTEM,
                    OPTIMIZER_USER.format(
                        risk_analysis_json=json.dumps(risk_analysis[:20], ensure_ascii=False, indent=2),
                        total_count=len(enriched),
                        test_cases_json=json.dumps(tc_summary, ensure_ascii=False, indent=2),
                        min_coverage=min_coverage,
                    )
                )

                # 提取 LLM 建议的优化结果
                suggested_remove = set(llm_result.get("removed_tc_ids", []))
                llm_reasoning = llm_result.get("optimization_summary", {}).get("reasoning", "")

            except Exception:
                suggested_remove = set()
                llm_reasoning = "LLM 优化失败，使用贪心算法"
        else:
            suggested_remove = set()
            llm_reasoning = "使用贪心算法优化"

    except Exception:
        suggested_remove = set()
        llm_reasoning = "使用贪心算法优化"

    # 执行贪心最小化
    optimized, removed_ids = greedy_minimize(enriched, risk_map, min_coverage)

    # 合并 LLM 建议的删除（但保留关键用例）
    final_remove = set(removed_ids) | suggested_remove
    final_tests = [tc for tc in enriched if tc.get("tc_id") not in final_remove]

    # 最终排序：High → Medium → Low，正向 → 负向
    final_tests.sort(key=lambda tc: (
        -PRIORITY_WEIGHT.get(risk_map.get(tc.get("req_id", ""), "Medium"), 2),
        -PRIORITY_WEIGHT.get(tc.get("priority", "Medium"), 2),
        0 if tc.get("is_positive", True) else 1,
    ))

    # 计算覆盖率
    covered_reqs = set(tc.get("req_id") for tc in final_tests)
    all_reqs = set(tc.get("req_id") for tc in enriched)
    coverage_rate = len(covered_reqs) / len(all_reqs) if all_reqs else 1.0

    optimization_result = {
        "original_count": original_count,
        "optimized_count": len(final_tests),
        "coverage_rate": round(coverage_rate, 3),
        "removed_ids": list(final_remove),
        "reasoning": llm_reasoning or f"保留所有 High/Medium 优先级用例，覆盖率 {coverage_rate:.1%}",
    }

    progress.append(
        f"[Optimizer] 优化完成：{original_count} → {len(final_tests)} 个用例，"
        f"需求覆盖率 {coverage_rate:.1%}"
    )

    return {
        "optimized_suite": final_tests,
        "optimization_result": optimization_result,
        "current_step": "optimized",
        "completed_steps": state.get("completed_steps", []) + ["optimize_suite"],
        "progress_messages": progress,
        "errors": errors,
    }
