"""Streamlit Dashboard - AutoTestDesign
Runs the workflow or loads outputs JSON and visualizes results.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv

# Ensure project root is on sys.path so local modules resolve correctly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env so API keys are available in Streamlit.
load_dotenv(PROJECT_ROOT / ".env")

from config import DEFAULT_CONFIG, OUTPUT_DIR, SAMPLE_REQUIREMENTS_TEXT
from graph.state import create_initial_state
from agents.input_parser import input_parser_node
from agents.requirement_structurer import requirement_structurer_node
from agents.risk_analyzer import risk_analyzer_node
from agents.blackbox_tester import blackbox_tester_node
from agents.whitebox_tester import whitebox_tester_node
from agents.oracle_generator import oracle_generator_node
from agents.optimizer import optimizer_node
from agents.exporter import exporter_node
from utils.visualizer import create_workflow_diagram


st.set_page_config(page_title="AutoTestDesign Dashboard", layout="wide")


def _pick_latest_output() -> Optional[Path]:
    files = list(OUTPUT_DIR.glob("*.json"))
    if not files:
        return None
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    root_tests = None
    if isinstance(payload.get("tests"), list) and payload["tests"]:
        root_tests = payload["tests"][0]

    summary = payload.get("summary") or {}
    if root_tests and not summary:
        summary = {
            "requirements_count": root_tests.get("structured_count") or root_tests.get("parsed_count"),
            "risk_items_count": root_tests.get("risk_count"),
            "blackbox_tests_count": root_tests.get("blackbox_test_count"),
            "whitebox_tests_count": root_tests.get("whitebox_test_count"),
            "optimized_suite_count": root_tests.get("optimized_suite_count"),
        }

    blackbox = root_tests.get("blackbox_tests") if root_tests else payload.get("blackbox_tests")
    whitebox = root_tests.get("whitebox_tests") if root_tests else payload.get("whitebox_tests")
    optimized = payload.get("optimized_suite")

    tests = []
    tests.extend(blackbox or [])
    tests.extend(whitebox or [])
    tests.extend(optimized or [])

    progress = payload.get("progress_messages") or payload.get("progress")
    if root_tests and not progress:
        progress = root_tests.get("progress_messages")

    export_artifact = payload.get("export_artifact") or payload.get("export_artifacts") or {}

    normalized = {
        "summary": {
            "requirements": summary.get("requirements_count") or len(payload.get("structured_requirements", [])),
            "risk": summary.get("risk_items_count") or len(payload.get("risk_analysis", [])),
            "blackbox": summary.get("blackbox_tests_count") or len(blackbox or []),
            "whitebox": summary.get("whitebox_tests_count") or len(whitebox or []),
            "optimized": summary.get("optimized_suite_count") or len(optimized or []),
        },
        "tests": tests,
        "progress": progress or [],
        "export_artifact": export_artifact,
        "meta": {
            "test_suite": payload.get("test_suite") or (root_tests.get("test_name") if root_tests else ""),
            "timestamp": payload.get("timestamp") or (root_tests.get("timestamp") if root_tests else ""),
        },
    }
    passthrough_keys = [
        "parsed_requirements",
        "structured_requirements",
        "risk_analysis",
        "blackbox_tests",
        "whitebox_tests",
        "state_models",
        "state_diagrams",
        "enriched_tests",
        "optimized_suite",
        "optimization_result",
        "errors",
    ]
    for key in passthrough_keys:
        if key in payload:
            normalized[key] = payload.get(key)
    return normalized


def _run_workflow(
    input_text: str,
    config: Dict[str, Any],
    emit: Optional[callable] = None,
) -> Dict[str, Any]:
    state = create_initial_state(raw_input=input_text, input_format="auto", config=config)
    progress: List[str] = []
    errors: List[str] = []

    def _emit(msg: str) -> None:
        progress.append(msg)
        if emit:
            emit(msg)
        print(msg, flush=True)

    _emit("[InputParser] 开始解析需求...")
    out = input_parser_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        _emit(msg)
    for msg in out.get("errors", []):
        errors.append(msg)
        _emit(msg)
    if out.get("errors"):
        raise RuntimeError("Input parsing failed. Check API key or input format.")

    _emit("[ReqStructurer] 开始结构化需求...")
    out = requirement_structurer_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        _emit(msg)
    for msg in out.get("errors", []):
        errors.append(msg)
        _emit(msg)
    if out.get("errors"):
        raise RuntimeError("Requirement structuring failed. Check API response.")

    _emit("[RiskAnalyzer] 开始风险评估...")
    out = risk_analyzer_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        _emit(msg)
    for msg in out.get("errors", []):
        errors.append(msg)
        _emit(msg)

    _emit("[BlackBox] 生成黑盒用例...")
    out_bb = blackbox_tester_node(state)
    _emit("[WhiteBox] 生成白盒用例...")
    out_wb = whitebox_tester_node(state)
    state.update(out_bb)
    state.update(out_wb)
    for msg in out_bb.get("progress_messages", []):
        _emit(msg)
    for msg in out_wb.get("progress_messages", []):
        _emit(msg)

    _emit("[Oracle] 生成预期结果...")
    out = oracle_generator_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        _emit(msg)

    _emit("[Optimizer] 优化测试套件...")
    out = optimizer_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        _emit(msg)

    _emit("[Exporter] 导出产物...")
    out = exporter_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        _emit(msg)

    payload = {
        "summary": {
            "requirements_count": len(state.get("structured_requirements", [])),
            "risk_items_count": len(state.get("risk_analysis", [])),
            "blackbox_tests_count": len(state.get("blackbox_tests", [])),
            "whitebox_tests_count": len(state.get("whitebox_tests", [])),
            "optimized_suite_count": len(state.get("optimized_suite", [])),
        },
        "parsed_requirements": state.get("parsed_requirements", []),
        "structured_requirements": state.get("structured_requirements", []),
        "risk_analysis": state.get("risk_analysis", []),
        "blackbox_tests": state.get("blackbox_tests", []),
        "whitebox_tests": state.get("whitebox_tests", []),
        "state_models": state.get("state_models", []),
        "state_diagrams": state.get("state_diagrams", {}),
        "enriched_tests": state.get("enriched_tests", []),
        "optimized_suite": state.get("optimized_suite", []),
        "optimization_result": state.get("optimization_result", {}),
        "progress_messages": progress,
        "errors": errors,
        "export_artifact": out.get("export_artifact", {}),
    }
    return _normalize_payload(payload)


if "payload" not in st.session_state:
    st.session_state.payload = None
    st.session_state.source = ""

st.title("AutoTestDesign Dashboard")

progress_container = st.container()

with st.sidebar:
    st.header("配置")
    config = DEFAULT_CONFIG.copy()
    config["min_coverage_rate"] = st.slider("最小覆盖率", 0.1, 1.0, 0.8)
    config["enable_state_transition"] = st.checkbox("启用状态转换", True)
    config["enable_bva"] = st.checkbox("启用边界值分析", True)

left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("需求输入")
    input_text = st.text_area("粘贴需求文本", value="", height=220)

    col_a, col_b, col_c = st.columns([1, 1, 2])
    with col_a:
        if st.button("运行工作流", type="primary"):
            status = progress_container.status("运行中...", expanded=True)
            try:
                st.session_state.payload = _run_workflow(
                    input_text,
                    config,
                    emit=lambda msg: status.write(msg),
                )
                st.session_state.source = "workflow"
                status.update(label="完成", state="complete")
            except Exception as exc:
                status.update(label="失败", state="error")
                st.error(f"运行失败: {exc}")
    with col_b:
        if st.button("加载最新输出"):
            latest = _pick_latest_output()
            if latest:
                data = json.loads(latest.read_text(encoding="utf-8"))
                st.session_state.payload = _normalize_payload(data)
                st.session_state.source = str(latest)
            else:
                st.warning("outputs/ 下没有 JSON 文件")
    with col_c:
        upload = st.file_uploader("上传 outputs JSON", type=["json"], label_visibility="collapsed")
        if upload:
            data = json.loads(upload.read().decode("utf-8"))
            st.session_state.payload = _normalize_payload(data)
            st.session_state.source = upload.name

with right:
    st.subheader("数据来源")
    source = st.session_state.source or "未加载"
    st.code(source)

payload = st.session_state.payload

if payload:
    summary = payload.get("summary", {})
    meta = payload.get("meta", {})

    st.markdown("---")
    st.subheader("摘要")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("需求", summary.get("requirements") or 0)
    m2.metric("风险项", summary.get("risk") or 0)
    m3.metric("黑盒用例", summary.get("blackbox") or 0)
    m4.metric("白盒用例", summary.get("whitebox") or 0)
    m5.metric("优化后", summary.get("optimized") or 0)

    if meta:
        meta_parts = []
        if meta.get("test_suite"):
            meta_parts.append(f"Suite: {meta['test_suite']}")
        if meta.get("timestamp"):
            meta_parts.append(f"Timestamp: {meta['timestamp']}")
        if meta_parts:
            st.caption(" | ".join(meta_parts))

    st.subheader("进度日志")
    progress = payload.get("progress", [])
    if progress:
        for msg in progress:
            st.info(msg)
    else:
        st.caption("暂无进度消息")

    if payload.get("errors"):
        st.subheader("错误")
        for msg in payload.get("errors", []):
            st.error(msg)

    st.subheader("测试用例")
    tests = payload.get("tests", [])
    if tests:
        techniques = sorted({tc.get("technique", "") for tc in tests if tc.get("technique")})
        priorities = sorted({tc.get("priority", "") for tc in tests if tc.get("priority")})
        reqs = sorted({tc.get("req_id", "") for tc in tests if tc.get("req_id")})

        f1, f2, f3 = st.columns(3)
        with f1:
            tech = st.selectbox("Technique", ["全部"] + techniques)
        with f2:
            priority = st.selectbox("Priority", ["全部"] + priorities)
        with f3:
            req_id = st.selectbox("Req ID", ["全部"] + reqs)

        filtered = tests
        if tech != "全部":
            filtered = [tc for tc in filtered if tc.get("technique") == tech]
        if priority != "全部":
            filtered = [tc for tc in filtered if tc.get("priority") == priority]
        if req_id != "全部":
            filtered = [tc for tc in filtered if tc.get("req_id") == req_id]

        table_rows = [
            {
                "TC ID": tc.get("tc_id"),
                "Req ID": tc.get("req_id"),
                "Technique": tc.get("technique"),
                "Title": tc.get("title"),
                "Priority": tc.get("priority"),
                "Positive": "Yes" if tc.get("is_positive", True) else "No",
            }
            for tc in filtered
        ]
        st.dataframe(table_rows, width="stretch", height=360)
    else:
        st.caption("暂无测试用例")

    st.subheader("导出产物")
    export_artifact = payload.get("export_artifact", {})
    if export_artifact:
        st.json(export_artifact)
    else:
        st.caption("暂无导出产物")

    st.subheader("Agent 输出")

    def _preview_list(items: List[Any], limit: int = 30) -> Dict[str, Any]:
        return {
            "count": len(items),
            "preview": items[:limit],
        }

    with st.expander("InputParser 输出", expanded=False):
        st.json(_preview_list(payload.get("parsed_requirements", [])))

    with st.expander("RequirementStructurer 输出", expanded=False):
        st.json(_preview_list(payload.get("structured_requirements", [])))

    with st.expander("RiskAnalyzer 输出", expanded=False):
        st.json(_preview_list(payload.get("risk_analysis", [])))

    with st.expander("BlackBox 输出", expanded=False):
        st.json(_preview_list(payload.get("blackbox_tests", [])))

    with st.expander("WhiteBox 输出", expanded=False):
        st.json(_preview_list(payload.get("whitebox_tests", [])))
        if payload.get("state_models"):
            st.caption("State Models")
            st.json(_preview_list(payload.get("state_models", [])))
        if payload.get("state_diagrams"):
            st.caption("State Diagrams (DOT)")
            st.json(payload.get("state_diagrams", {}))

    with st.expander("Oracle 输出", expanded=False):
        st.json(_preview_list(payload.get("enriched_tests", [])))

    with st.expander("Optimizer 输出", expanded=False):
        st.json(_preview_list(payload.get("optimized_suite", [])))
        if payload.get("optimization_result"):
            st.caption("Optimization Result")
            st.json(payload.get("optimization_result", {}))

else:
    st.info("运行工作流或加载 outputs JSON 后显示结果。")

