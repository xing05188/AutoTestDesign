"""
AutoTestDesign - InputParserAgent (FR1.0)
负责解析多种格式的需求输入，统一为内部表示
"""

import csv
import io
from typing import List, Dict, Any

from utils.llm_client import get_shared_llm, call_llm_json
from prompts.templates import INPUT_PARSER_SYSTEM, INPUT_PARSER_USER
from graph.state import AutoTestState


def parse_csv_input(raw_input: str) -> List[Dict]:
    """直接解析 CSV 格式的需求（不经过 LLM，更精确）"""
    requirements = []
    try:
        reader = csv.DictReader(io.StringIO(raw_input))
        for i, row in enumerate(reader, 1):
            # 兼容常见字段名
            req_id = (
                row.get("req_id") or row.get("id") or row.get("ID") or f"REQ-{i:03d}"
            )
            title = (
                row.get("title") or row.get("Title") or row.get("name") or f"需求{i}"
            )
            description = (
                row.get("description") or row.get("Description") or
                row.get("desc") or row.get("requirement") or ""
            )
            requirements.append({
                "req_id": str(req_id).strip(),
                "title": str(title).strip(),
                "description": str(description).strip(),
                "source": str(row),
            })
    except Exception as e:
        # CSV 解析失败，返回空列表让 LLM 处理
        return []
    return requirements


def is_csv_format(raw_input: str) -> bool:
    """检测是否为 CSV 格式"""
    lines = raw_input.strip().split('\n')
    if len(lines) < 2:
        return False
    # 首行有逗号分隔且包含常见字段名
    header = lines[0].lower()
    return ',' in header and any(
        kw in header for kw in ['id', 'req', 'title', 'description', 'requirement']
    )


def input_parser_node(state: AutoTestState) -> Dict[str, Any]:
    """
    LangGraph 节点函数
    解析原始输入 → parsed_requirements
    
    改进：所有格式（包括 CSV）都通过 LLM 解析，以处理任意字段名
    """
    raw_input = state["raw_input"]
    input_format = state.get("input_format", "auto")

    progress = ["[InputParser] 开始解析需求输入..."]
    errors = []

    try:
        # 自动检测格式（仅用于日志，不影响解析策略）
        detected_format = "csv" if (input_format == "csv" or (input_format == "auto" and is_csv_format(raw_input))) else "text"
        
        # 统一使用 LLM 解析所有格式
        llm = get_shared_llm()
        result = call_llm_json(
            llm,
            INPUT_PARSER_SYSTEM,
            INPUT_PARSER_USER.format(
                input_format=detected_format if input_format == "auto" else input_format,
                raw_input=raw_input,
            )
        )

        # 确保结果是列表
        if isinstance(result, dict) and "requirements" in result:
            result = result["requirements"]
        if not isinstance(result, list):
            result = [result]

        progress.append(f"[InputParser] LLM 解析完成，提取 {len(result)} 条需求（检测格式: {detected_format}）")

        return {
            "parsed_requirements": result,
            "input_format": detected_format,
            "current_step": "parsed",
            "completed_steps": state.get("completed_steps", []) + ["parse_input"],
            "progress_messages": progress,
            "errors": [],
        }

    except Exception as e:
        error_msg = f"[InputParser] 解析失败: {str(e)}"
        errors.append(error_msg)
        return {
            "parsed_requirements": [],
            "current_step": "error",
            "progress_messages": progress,
            "errors": errors,
        }
