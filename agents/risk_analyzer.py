"""
AutoTestDesign - RiskAnalyzerAgent (FR2.0)
为每条需求分配风险评分和测试优先级
"""

import json
from typing import List, Dict, Any

from utils.llm_client import get_shared_llm, call_llm_json
from prompts.templates import RISK_ANALYZER_SYSTEM, RISK_ANALYZER_USER
from graph.state import AutoTestState


def calculate_risk_score(impact: int, probability: int, complexity: int, change_frequency: int = 5) -> float:
    """
    计算综合风险分（多维度加权公式）
    风险分 = impact×0.4 + probability×0.3 + complexity×0.2 + change_frequency×0.1
    """
    return round(impact * 0.4 + probability * 0.3 + complexity * 0.2 + change_frequency * 0.1, 1)


def determine_priority(risk_score: float, config: Dict) -> str:
    high_threshold = config.get("risk_threshold_high", 7.0)
    medium_threshold = config.get("risk_threshold_medium", 4.0)
    if risk_score >= high_threshold:
        return "High"
    elif risk_score >= medium_threshold:
        return "Medium"
    else:
        return "Low"


def validate_risk_item(item: Dict, config: Dict) -> Dict:
    """验证并修正风险评分数据"""
    # 确保评分在 1-10 范围内
    impact = max(1, min(10, int(item.get("impact", 5))))
    probability = max(1, min(10, int(item.get("probability", 5))))
    complexity = max(1, min(10, int(item.get("complexity", 5))))
    change_frequency = max(1, min(10, int(item.get("change_frequency", 5))))

    # 重新计算确保一致性（使用新的 4 维度公式）
    risk_score = calculate_risk_score(impact, probability, complexity, change_frequency)
    priority = determine_priority(risk_score, config)

    return {
        "req_id": item.get("req_id", "UNKNOWN"),
        "title": item.get("title", ""),
        "impact": impact,
        "probability": probability,
        "complexity": complexity,
        "change_frequency": change_frequency,
        "risk_score": risk_score,
        "priority": priority,
        "risk_factors": item.get("risk_factors", []),
        "mitigation": item.get("mitigation", ""),
    }


def risk_analyzer_node(state: AutoTestState) -> Dict[str, Any]:
    """
    LangGraph 节点函数
    structured_requirements → risk_analysis
    """
    structured = state.get("structured_requirements", [])
    config = state.get("config", {})
    progress = ["[RiskAnalyzer] 开始风险评估分析..."]
    errors = []

    if not structured:
        errors.append("[RiskAnalyzer] 没有可用的结构化需求")
        return {
            "risk_analysis": [],
            "current_step": "error",
            "progress_messages": progress,
            "errors": errors,
        }

    try:
        llm = get_shared_llm()

        # 批量风险评估（每批 8 条）
        all_risks = []
        batch_size = 8

        for i in range(0, len(structured), batch_size):
            batch = structured[i: i + batch_size]
            try:
                result = call_llm_json(
                    llm,
                    RISK_ANALYZER_SYSTEM,
                    RISK_ANALYZER_USER.format(
                        requirements_json=json.dumps(batch, ensure_ascii=False, indent=2)
                    )
                )

                if isinstance(result, dict) and "risks" in result:
                    result = result["risks"]
                if isinstance(result, list):
                    all_risks.extend(result)
                else:
                    all_risks.append(result)

            except Exception as e:
                # 批次失败时，生成默认风险评分
                for req in batch:
                    all_risks.append({
                        "req_id": req.get("req_id", "UNKNOWN"),
                        "title": req.get("title", ""),
                        "impact": 5,
                        "probability": 5,
                        "complexity": 5,
                        "risk_factors": ["评估失败，使用默认值"],
                        "mitigation": "需要手动评估",
                    })

        # 验证和规范化
        validated_risks = [validate_risk_item(r, config) for r in all_risks]

        # 统计
        high_count = sum(1 for r in validated_risks if r["priority"] == "High")
        medium_count = sum(1 for r in validated_risks if r["priority"] == "Medium")
        low_count = sum(1 for r in validated_risks if r["priority"] == "Low")

        progress.append(
            f"[RiskAnalyzer] 风险评估完成：高风险 {high_count} 条，"
            f"中风险 {medium_count} 条，低风险 {low_count} 条"
        )

        return {
            "risk_analysis": validated_risks,
            "current_step": "risk_analyzed",
            "completed_steps": state.get("completed_steps", []) + ["analyze_risk"],
            "progress_messages": progress,
            "errors": [],
        }

    except Exception as e:
        error_msg = f"[RiskAnalyzer] 风险分析失败: {str(e)}"
        errors.append(error_msg)

        # Fallback：所有需求标记为中等风险
        fallback = [
            validate_risk_item({
                "req_id": r.get("req_id", f"REQ-{i+1:03d}"),
                "title": r.get("title", ""),
                "impact": 5, "probability": 5, "complexity": 5,
                "risk_factors": ["未能完成 AI 分析，使用默认评分"],
                "mitigation": "建议手动审查",
            }, config)
            for i, r in enumerate(structured)
        ]

        return {
            "risk_analysis": fallback,
            "current_step": "risk_analyzed_fallback",
            "completed_steps": state.get("completed_steps", []) + ["analyze_risk"],
            "progress_messages": progress + ["[RiskAnalyzer] 使用 Fallback 风险评分"],
            "errors": errors,
        }
