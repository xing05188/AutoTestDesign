"""Streamlit Dashboard - AutoTestDesign
黑盒测试工作流 + 白盒测试（测试代码生成 & 最优测试序列生成）。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv

# Ensure project root is on sys.path so local modules resolve correctly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Add agents/whitebox to sys.path for direct imports
_WHITEBOX_DIR = PROJECT_ROOT / "agents" / "whitebox"
if str(_WHITEBOX_DIR) not in sys.path:
    sys.path.insert(0, str(_WHITEBOX_DIR))

# Load .env so API keys are available in Streamlit.
load_dotenv(PROJECT_ROOT / ".env")

from config import DEFAULT_CONFIG, SAMPLE_REQUIREMENTS_TEXT
from graph.state import create_initial_state
from agents.input_parser import input_parser_node
from agents.requirement_structurer import requirement_structurer_node
from agents.risk_analyzer import risk_analyzer_node
from agents.blackbox_tester import blackbox_tester_node
from agents.oracle_generator import oracle_generator_node
from agents.optimizer import optimizer_node
from agents.exporter import exporter_node
from utils.visualizer import create_workflow_diagram

st.set_page_config(page_title="AutoTestDesign Dashboard", layout="wide")


# ──────────────────────────────────────────────────────────────────
# Helper functions (existing)
# ──────────────────────────────────────────────────────────────────

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
            "optimized_suite_count": root_tests.get("optimized_suite_count"),
        }

    blackbox = root_tests.get("blackbox_tests") if root_tests else payload.get("blackbox_tests")
    optimized = payload.get("optimized_suite")

    tests = []
    tests.extend(blackbox or [])
    tests.extend(optimized or [])

    progress = payload.get("progress_messages") or payload.get("progress")
    if root_tests and not progress:
        progress = root_tests.get("progress_messages")

    normalized = {
        "summary": {
            "requirements": summary.get("requirements_count") or len(payload.get("structured_requirements", [])),
            "risk": summary.get("risk_items_count") or len(payload.get("risk_analysis", [])),
            "blackbox": summary.get("blackbox_tests_count") or len(blackbox or []),
            "optimized": summary.get("optimized_suite_count") or len(optimized or []),
        },
        "tests": tests,
        "progress": progress or [],
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
    session_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "outputs",
        datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    os.makedirs(session_dir, exist_ok=True)

    state = create_initial_state(raw_input=input_text, input_format="auto", config=config)
    state["session_dir"] = session_dir
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
    state.update(out_bb)
    for msg in out_bb.get("progress_messages", []):
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
            "optimized_suite_count": len(state.get("optimized_suite", [])),
        },
        "parsed_requirements": state.get("parsed_requirements", []),
        "structured_requirements": state.get("structured_requirements", []),
        "risk_analysis": state.get("risk_analysis", []),
        "blackbox_tests": state.get("blackbox_tests", []),
        "enriched_tests": state.get("enriched_tests", []),
        "optimized_suite": state.get("optimized_suite", []),
        "optimization_result": state.get("optimization_result", {}),
        "progress_messages": progress,
        "errors": errors,
    }
    return _normalize_payload(payload)


# ──────────────────────────────────────────────────────────────────
# Whitebox helpers
# ──────────────────────────────────────────────────────────────────

def _get_api_config() -> dict:
    """Get API configuration from environment, with fallbacks for whitebox."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    api_base = os.environ.get("OPENAI_API_URL", "")
    model = os.environ.get("OPENAI_MODEL", "")
    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_base:
        api_base = os.environ.get("DEEPSEEK_API_URL", "")
    if not model:
        model = os.environ.get("DEEPSEEK_MODEL", "")
    return {"api_key": api_key, "api_base": api_base, "model": model}


def _run_test_generation(
    source_path: str,
    output_dir: str,
    scheme: str,
    stmt_max_iter: int,
    br_max_iter: int,
    br_target: float,
    min_coverage_rate: float,
    status_slot,
) -> dict:
    """Run whitebox test code generation and return results.

    The source file must already exist at ``source_path`` inside a
    ``source_file/`` subdirectory so coverage measurement targets only
    that single file.
    """
    from whitebox_test import WhiteboxTestRunner

    source_path = Path(source_path).resolve()
    output_dir = Path(output_dir).resolve()
    source_name = source_path.stem

    # Create isolated subdirectory for the source file
    work_dir = output_dir / source_name
    work_dir.mkdir(parents=True, exist_ok=True)

    # Ensure source file lives inside a dedicated source_file/ subdirectory
    source_subdir = work_dir / "source_file"
    source_subdir.mkdir(parents=True, exist_ok=True)
    dest_source = source_subdir / source_path.name
    if source_path != dest_source:
        shutil.copy2(source_path, dest_source)
        status_slot.write(f"已将源代码复制到: {dest_source}")
    else:
        status_slot.write(f"源代码路径: {dest_source}")

    # Test file path — in source_file/ alongside the source so imports resolve
    test_file = source_subdir / f"test_{source_name}.py"
    status_slot.write(f"测试文件路径: {test_file}")

    # Build API config
    api = _get_api_config()
    if not api["api_key"]:
        raise RuntimeError("未找到 API key，请设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY 环境变量")

    status_slot.write(f"启动白盒测试运行器 (模式: {scheme})...")

    runner = WhiteboxTestRunner(
        source_file=str(dest_source),
        test_file=str(test_file),
        mode=scheme,
        api_key=api["api_key"],
        api_base=api["api_base"],
        model=api["model"],
        project_root=str(PROJECT_ROOT),
        statement_target=str(int(min_coverage_rate * 100)),
        statement_max_iterations=str(stmt_max_iter),
        statement_max_run_time="60",
        branch_target=float(br_target),
        branch_max_iterations=br_max_iter,
        include_conditions=(scheme == "full"),
    )

    # Save cwd and restore after run (runner changes directory)
    saved_cwd = os.getcwd()
    try:
        result = runner.run()
    finally:
        os.chdir(saved_cwd)

    # Read generated test code
    test_code = ""
    if test_file.exists():
        test_code = test_file.read_text(encoding="utf-8")

    # Read coverage report
    coverage_md = ""
    report_path = runner.report_path
    if report_path.exists():
        coverage_md = report_path.read_text(encoding="utf-8")

    return {
        "scheme": scheme,
        "source_name": source_name,
        "work_dir": str(work_dir),
        "test_file": str(test_file),
        "test_code": test_code,
        "coverage_md": coverage_md,
        "report_path": str(report_path),
        "result_dir": str(runner.result_dir),
        "runner_result": result,
    }


def _run_optimal_sequence(
    requirements: str,
    diagram_output_dir: str,
    criterion_name: str,
    status_slot,
) -> dict:
    """Run state transition analysis and optimal sequence generation."""
    from state_transition import StateTransitionAnalyzer
    from optimal_sequence import CoverageCriterion, generate_optimal_sequence

    api = _get_api_config()
    if not api["api_key"]:
        raise RuntimeError("未找到 API key，请设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY 环境变量")

    # Criterion mapping
    criterion_map = {
        "全状态覆盖": CoverageCriterion.ALL_STATES,
        "全转换覆盖": CoverageCriterion.ALL_TRANSITIONS,
        "转换对覆盖": CoverageCriterion.ALL_TRANSITION_PAIRS,
        "全路径覆盖": CoverageCriterion.ALL_PATHS,
    }
    criterion = criterion_map[criterion_name]

    status_slot.write("正在通过 LLM 分析需求，提取状态转换图...")
    analyzer = StateTransitionAnalyzer(
        api_key=api["api_key"],
        api_base=api["api_base"],
        model=api["model"],
    )
    diagram = analyzer.analyze(requirements)

    status_slot.write(f"状态转换图已生成: {diagram.title}, {len(diagram.states)} 个状态, {len(diagram.transitions)} 个转换")

    # Render diagram as PNG
    diagram_output_dir = Path(diagram_output_dir).resolve()
    diagram_output_dir.mkdir(parents=True, exist_ok=True)
    image_path = None
    mermaid_code = diagram.to_mermaid()
    try:
        image_path = diagram.render(str(diagram_output_dir / diagram.title), format="png")
        status_slot.write(f"状态转换图已渲染: {image_path}")
    except Exception as exc:
        status_slot.write(f"图像渲染失败 (可能未安装 Graphviz): {exc}")

    # Generate optimal sequence (algorithmic, no LLM needed)
    status_slot.write(f"正在生成最优测试序列 (准则: {criterion_name})...")
    sequence = generate_optimal_sequence(diagram, criterion, use_llm=False)

    return {
        "diagram": diagram,
        "diagram_json": diagram.to_json(),
        "diagram_dict": diagram.to_dict(),
        "mermaid_code": mermaid_code,
        "image_path": image_path,
        "sequence": sequence,
        "sequence_table": sequence.to_table(),
        "sequence_text": sequence.to_text(),
        "sequence_json": sequence.to_json(),
        "state_sequence": sequence.get_state_sequence(),
        "criterion": criterion_name,
    }


# ──────────────────────────────────────────────────────────────────
# Session state init
# ──────────────────────────────────────────────────────────────────

if "payload" not in st.session_state:
    st.session_state.payload = None

# Whitebox state
if "wb_gen_result" not in st.session_state:
    st.session_state.wb_gen_result = None
if "bb_seq_result" not in st.session_state:
    st.session_state.bb_seq_result = None
if "wb_seq_result" not in st.session_state:
    st.session_state.wb_seq_result = None

st.title("AutoTestDesign Dashboard")

# ──────────────────────────────────────────────────────────────────
# Sidebar (shared across tabs)
# ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("配置")
    enable_ep = st.checkbox("等价类划分 (EP)", True, key="sidebar_ep")
    enable_bva = st.checkbox("边界值分析 (BVA)", True, key="sidebar_bva")
    enable_dt = st.checkbox("决策表 (Decision Table)", True, key="sidebar_dt")

    blackbox_config = DEFAULT_CONFIG.copy()
    blackbox_config["enable_ep"] = enable_ep
    blackbox_config["enable_bva"] = enable_bva
    blackbox_config["enable_decision_table"] = enable_dt
    st.session_state["blackbox_config"] = blackbox_config

# ──────────────────────────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────────────────────────

tab_blackbox, tab_bb_sequence, tab_wb_codegen, tab_wb_sequence = st.tabs([
    "黑盒测试",
    "黑盒测试 - 最优测试序列",
    "白盒测试 - 测试代码生成",
    "白盒测试 - 最优测试序列",
])

# ══════════════════════════════════════════════════════════════════
# Tab 1: Black-Box Testing (existing)
# ══════════════════════════════════════════════════════════════════

with tab_blackbox:
    config = st.session_state.get("blackbox_config", DEFAULT_CONFIG.copy())

    with st.container(border=True):
        st.subheader("需求输入")
        input_text = st.text_area("粘贴需求文本", value="", height=180, label_visibility="collapsed")
        col_run, col_up = st.columns([1, 3])
        with col_run:
            if st.button("运行工作流", type="primary"):
                st.session_state._trigger_run = True
        with col_up:
            upload = st.file_uploader("上传 JSON", type=["json"], label_visibility="collapsed")
            if upload:
                data = json.loads(upload.read().decode("utf-8"))
                st.session_state.payload = _normalize_payload(data)

    status_placeholder = st.empty()

    if st.session_state.pop("_trigger_run", False):
        try:
            with status_placeholder.status("运行中...", expanded=True) as status:
                st.session_state.payload = _run_workflow(
                    input_text,
                    config,
                    emit=lambda msg: status.write(msg),
                )
                status.update(label="完成", state="complete")
        except Exception as exc:
            status_placeholder.error(f"运行失败: {exc}")

    st.markdown("---")
    payload = st.session_state.payload

    if payload:
        summary = payload.get("summary", {})
        meta = payload.get("meta", {})

        st.subheader("摘要")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("需求", summary.get("requirements") or 0)
        m2.metric("风险项", summary.get("risk") or 0)
        m3.metric("黑盒用例", summary.get("blackbox") or 0)
        m4.metric("优化后", summary.get("optimized") or 0)

        if meta:
            meta_parts = []
            if meta.get("test_suite"):
                meta_parts.append(f"Suite: {meta['test_suite']}")
            if meta.get("timestamp"):
                meta_parts.append(f"Timestamp: {meta['timestamp']}")
            if meta_parts:
                st.caption(" | ".join(meta_parts))

        st.markdown("---")
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
            st.dataframe(table_rows, use_container_width=True, height=360)
        else:
            st.caption("暂无测试用例")

        st.markdown("---")
        st.subheader("Agent 输出")

        with st.expander("InputParser 输出 — 原始需求列表", expanded=False):
            items = payload.get("parsed_requirements", [])
            if items:
                for i, item in enumerate(items):
                    st.markdown(f"**{i+1}. {item.get('req_id', item.get('title', f'需求 {i+1}'))}**")
                    st.markdown(f"{item.get('description', item.get('content', ''))}")
                    st.markdown("---")
            else:
                st.caption("无数据")

        with st.expander("RequirementStructurer 输出 — 结构化需求", expanded=False):
            items = payload.get("structured_requirements", [])
            if items:
                for i, item in enumerate(items):
                    with st.expander(f"{i+1}. {item.get('req_id', item.get('title', f'需求 {i+1}'))}", expanded=False):
                        for key, val in item.items():
                            if val:
                                st.markdown(f"**{key}**: {val}")
            else:
                st.caption("无数据")

        with st.expander("RiskAnalyzer 输出 — 风险评估", expanded=False):
            items = payload.get("risk_analysis", [])
            if items:
                risk_rows = [
                    {
                        "Req ID": r.get("req_id", ""),
                        "风险评分": r.get("risk_score", r.get("score", "")),
                        "风险等级": r.get("risk_level", r.get("level", "")),
                        "测试优先级": r.get("test_priority", r.get("priority", "")),
                        "说明": r.get("reason", r.get("description", "")),
                    }
                    for r in items
                ]
                st.dataframe(risk_rows, use_container_width=True)
            else:
                st.caption("无数据")

        with st.expander("BlackBox 输出 — 黑盒测试用例", expanded=False):
            items = payload.get("blackbox_tests", [])
            if items:
                for i, tc in enumerate(items):
                    with st.expander(f"{tc.get('tc_id', f'TC-{i+1}')} — {tc.get('title', '')}", expanded=False):
                        cols = st.columns(2)
                        with cols[0]:
                            st.markdown(f"**Req ID**: {tc.get('req_id', '-')}")
                            st.markdown(f"**Technique**: {tc.get('technique', '-')}")
                            st.markdown(f"**Priority**: {tc.get('priority', '-')}")
                            st.markdown(f"**前置条件**: {tc.get('precondition', tc.get('preconditions', '-'))}")
                        with cols[1]:
                            st.markdown(f"**Positive**: {'Yes' if tc.get('is_positive', True) else 'No'}")
                            st.markdown(f"**输入数据**: {tc.get('input_data', tc.get('inputs', '-'))}")
                            st.markdown(f"**预期结果**: {tc.get('expected_result', tc.get('expected', '-'))}")
            else:
                st.caption("无数据")

        with st.expander("Oracle 输出 — 预期结果增强", expanded=False):
            items = payload.get("enriched_tests", [])
            if items:
                for i, tc in enumerate(items):
                    with st.expander(f"{tc.get('tc_id', f'TC-{i+1}')} — {tc.get('title', '')}", expanded=False):
                        for key, val in tc.items():
                            if val:
                                st.markdown(f"**{key}**: {val}")
            else:
                st.caption("无数据")

        with st.expander("Optimizer 输出 — 优化结果", expanded=False):
            suite = payload.get("optimized_suite", [])
            if suite:
                opt_rows = [
                    {
                        "TC ID": tc.get("tc_id", ""),
                        "Title": tc.get("title", ""),
                        "Priority": tc.get("priority", ""),
                    }
                    for tc in suite
                ]
                st.dataframe(opt_rows, use_container_width=True)
            else:
                st.caption("无数据")
            if payload.get("optimization_result"):
                opt = payload["optimization_result"]
                st.markdown("**优化详情**")
                for key, val in opt.items():
                    if isinstance(val, dict):
                        st.markdown(f"**{key}**:")
                        st.json(val)
                    else:
                        st.markdown(f"**{key}**: {val}")

        st.markdown("---")
        with st.expander("进度日志", expanded=False):
            progress = payload.get("progress", [])
            if progress:
                st.code("\n".join(progress))
            else:
                st.caption("暂无进度消息")

        if payload.get("errors"):
            for msg in payload.get("errors", []):
                st.error(msg)
    else:
        status_placeholder.info("运行工作流或加载 outputs JSON 后显示结果。")


# ══════════════════════════════════════════════════════════════════
# Tab 3: Whitebox - Test Code Generation
# ══════════════════════════════════════════════════════════════════

with tab_wb_codegen:
    st.header("白盒测试代码生成")
    st.markdown("基于源代码自动生成白盒测试用例。支持**语句覆盖**和**全覆盖**（语句 + 分支 + 条件/MC-DC）两种方案。")

    col_cfg, col_result = st.columns([1, 1], gap="large")

    with col_cfg:
        st.subheader("配置参数")

        uploaded_file = st.file_uploader(
            "上传源代码文件 (.py)",
            type=["py"],
            key="wb_codegen_upload",
            help="选择要生成测试的 Python 源代码文件",
        )

        scheme = st.radio(
            "生成方案",
            options=["statement", "full"],
            format_func=lambda x: "仅语句覆盖 (statement)" if x == "statement" else "全覆盖 — 语句 + 分支 + 条件 (full)",
            key="wb_codegen_scheme",
            help="statement: 仅语句覆盖; full: 语句+分支+条件(MC/DC)全覆盖",
        )

        default_out = "outputs"
        output_dir = st.text_input(
            "输出目录",
            value=default_out,
            key="wb_codegen_outdir",
            help="测试代码和覆盖率报告将输出到此目录下的子目录中",
        )

        st.caption("— 语句覆盖参数 —")
        stmt_max_iter = st.number_input(
            "语句覆盖最大迭代次数",
            min_value=1,
            max_value=50,
            value=10,
            key="wb_codegen_stmt_iter",
            help="qodo-cover 的最大迭代次数",
        )

        if scheme == "full":
            st.caption("— 分支/条件覆盖参数 —")
            br_col1, br_col2 = st.columns(2)
            with br_col1:
                br_max_iter = st.number_input(
                    "分支覆盖最大迭代次数",
                    min_value=1,
                    max_value=20,
                    value=3,
                    key="wb_codegen_br_iter",
                    help="CoverageImprovementPipeline 最大迭代次数",
                )
            with br_col2:
                cov_default = int(st.session_state.get("min_coverage_rate", 0.8) * 100)
                br_target = st.slider(
                    "分支覆盖率目标 (%)",
                    min_value=50,
                    max_value=100,
                    value=cov_default,
                    key="wb_codegen_br_target",
                )

        run_disabled = uploaded_file is None
        if st.button("开始生成测试代码", type="primary", disabled=run_disabled, key="wb_codegen_run"):
            status = st.status("运行中...", expanded=True)
            try:
                # Save uploaded file in a dedicated source_file/ subdirectory
                # so coverage measurement targets only this one file.
                original_name = Path(uploaded_file.name).name
                source_stem = Path(original_name).stem
                out_dir = Path(output_dir)
                work_dir = out_dir / source_stem
                source_subdir = work_dir / "source_file"
                source_subdir.mkdir(parents=True, exist_ok=True)

                source_path = source_subdir / original_name
                source_path.write_bytes(uploaded_file.getvalue())
                status.write(f"源代码已保存: {source_path}")

                st.session_state.wb_gen_result = _run_test_generation(
                    source_path=str(source_path),
                    output_dir=output_dir,
                    scheme=scheme,
                    stmt_max_iter=stmt_max_iter,
                    br_max_iter=br_max_iter if scheme == "full" else 3,
                    br_target=br_target if scheme == "full" else 90.0,
                    min_coverage_rate=st.session_state.get("min_coverage_rate", 0.8),
                    status_slot=status,
                )

                status.update(label="生成完成", state="complete")
            except Exception as exc:
                status.update(label="生成失败", state="error")
                st.error(f"运行失败: {exc}")

    with col_result:
        st.subheader("生成结果")
        result = st.session_state.wb_gen_result

        if result:
            scheme_label = "仅语句覆盖" if result["scheme"] == "statement" else "全覆盖 (语句+分支+条件)"
            st.success(f"方案: {scheme_label} | 源代码: {result['source_name']}.py")

            # --- Test code ---
            st.markdown("#### 生成的测试代码")
            if result["test_code"]:
                st.code(result["test_code"], language="python", line_numbers=True)
                st.caption(f"测试文件: {result['test_file']}")
            else:
                st.warning("测试代码文件未找到")

            # --- Coverage report ---
            st.markdown("#### 覆盖率报告")
            if result["coverage_md"]:
                with st.expander("查看覆盖率报告 (Markdown)", expanded=True):
                    st.markdown(result["coverage_md"])
            else:
                st.warning("覆盖率报告未生成")

            # --- File locations ---
            st.markdown("#### 输出文件位置")
            st.caption(f"工作目录: {result['work_dir']}")
            st.caption(f"结果目录: {result['result_dir']}")
            st.caption(f"报告文件: {result['report_path']}")
        else:
            st.info('上传源代码文件并点击「开始生成测试代码」后，结果将显示在这里。')


# ══════════════════════════════════════════════════════════════════
# Tab 2: Black-Box - Optimal Test Sequence
# ══════════════════════════════════════════════════════════════════

with tab_bb_sequence:
    st.header("黑盒测试 - 最优测试序列生成")
    st.markdown("基于**需求文档**通过 LLM 自动提取状态转换图，并使用图算法生成最优测试序列。")

    col_cfg, col_result = st.columns([1, 1], gap="large")

    with col_cfg:
        st.subheader("配置参数")

        req_text = st.text_area(
            "需求文档",
            value="",
            height=220,
            key="bb_seq_req",
            help="输入描述状态转换的需求文档（中文/英文均可）",
            placeholder="例如：用户登录系统需求：\n1. 系统初始处于「未登录」状态。\n2. 用户点击登录后进入「验证中」状态。\n3. 验证成功进入「已登录」，失败回到「未登录」...",
        )

        default_diagram_dir = "outputs/diagrams"
        diagram_dir = st.text_input(
            "状态转换图输出目录",
            value=default_diagram_dir,
            key="bb_seq_diagram_dir",
            help="状态转换图 PNG 图片将保存到此目录",
        )

        criterion = st.selectbox(
            "覆盖准则",
            options=["全状态覆盖", "全转换覆盖", "转换对覆盖", "全路径覆盖"],
            index=1,
            key="bb_seq_criterion",
            help="全状态覆盖=访问所有状态; 全转换覆盖=遍历所有转换(推荐); 转换对覆盖=覆盖相邻转换对; 全路径覆盖=所有无环路径",
        )

        run_disabled = not req_text.strip()
        if st.button("生成状态图与最优序列", type="primary", disabled=run_disabled, key="bb_seq_run"):
            status = st.status("运行中...", expanded=True)
            try:
                st.session_state.bb_seq_result = _run_optimal_sequence(
                    requirements=req_text,
                    diagram_output_dir=diagram_dir,
                    criterion_name=criterion,
                    status_slot=status,
                )
                status.update(label="生成完成", state="complete")
            except Exception as exc:
                status.update(label="生成失败", state="error")
                st.error(f"运行失败: {exc}")

    with col_result:
        st.subheader("生成结果")
        result = st.session_state.bb_seq_result

        if result:
            diagram = result["diagram"]
            sequence = result["sequence"]

            # --- State transition diagram ---
            st.markdown("#### 状态转换图")

            tab_diagram_img, tab_diagram_mermaid, tab_diagram_json = st.tabs([
                "状态图", "Mermaid 代码", "JSON",
            ])

            with tab_diagram_img:
                if result["image_path"] and Path(result["image_path"]).exists():
                    st.image(result["image_path"], caption=diagram.title, use_container_width=True)
                else:
                    st.info("未能渲染状态图图片（可能 Graphviz 未安装）。请查看下方 Mermaid 代码。")
                    st.code(result["mermaid_code"], language="mermaid")

            with tab_diagram_mermaid:
                st.code(result["mermaid_code"], language="mermaid")

            with tab_diagram_json:
                st.json(result["diagram_dict"])

            # --- State & transition summary ---
            st.markdown("#### 状态与转换摘要")
            sm1, sm2, sm3 = st.columns(3)
            sm1.metric("状态数", len(diagram.states))
            sm2.metric("转换数", len(diagram.transitions))
            sm3.metric("覆盖准则", result["criterion"])

            # --- Optimal test sequence ---
            st.markdown("#### 最优测试序列")
            st.markdown(f"**序列长度**: {len(sequence.steps)} 步 | **状态路径**: {' → '.join(result['state_sequence'])}")

            # Build table rows
            seq_rows = []
            for step in sequence.steps:
                seq_rows.append({
                    "步骤": step.step,
                    "动作/触发器": step.action,
                    "起始状态": step.from_state,
                    "目标状态": step.to_state,
                    "守卫条件": step.guard if step.guard else "-",
                    "预期结果": step.expected if step.expected else f"进入'{step.to_state}'状态",
                })
            st.dataframe(seq_rows, use_container_width=True, height=360)

            # --- Detailed table ---
            with st.expander("查看详细测试序列表 (Markdown 表格)", expanded=False):
                st.markdown(sequence.to_table())

            # --- JSON export ---
            with st.expander("查看 JSON 导出", expanded=False):
                st.json(json.loads(sequence.to_json()))
        else:
            st.info('输入需求文档并点击「生成状态图与最优序列」后，结果将显示在这里。')


# ══════════════════════════════════════════════════════════════════
# Tab 4: Whitebox - Optimal Test Sequence
# ══════════════════════════════════════════════════════════════════

with tab_wb_sequence:
    st.header("白盒测试 - 最优测试序列生成")
    st.markdown("基于**源代码**通过 LLM 自动提取状态转换图，并使用图算法生成最优测试序列。")

    col_cfg, col_result = st.columns([1, 1], gap="large")

    with col_cfg:
        st.subheader("配置参数")

        uploaded_file = st.file_uploader(
            "上传源代码文件 (.py)",
            type=["py"],
            key="wb_seq_upload",
            help="选择要分析状态转换的 Python 源代码文件",
        )

        default_diagram_dir = "outputs/diagrams"
        diagram_dir = st.text_input(
            "状态转换图输出目录",
            value=default_diagram_dir,
            key="wb_seq_diagram_dir",
            help="状态转换图 PNG 图片将保存到此目录",
        )

        criterion = st.selectbox(
            "覆盖准则",
            options=["全状态覆盖", "全转换覆盖", "转换对覆盖", "全路径覆盖"],
            index=1,
            key="wb_seq_criterion",
            help="全状态覆盖=访问所有状态; 全转换覆盖=遍历所有转换(推荐); 转换对覆盖=覆盖相邻转换对; 全路径覆盖=所有无环路径",
        )

        run_disabled = uploaded_file is None
        if st.button("生成状态图与最优序列", type="primary", disabled=run_disabled, key="wb_seq_run"):
            status = st.status("运行中...", expanded=True)
            try:
                source_code = uploaded_file.getvalue().decode("utf-8")
                st.session_state.wb_seq_result = _run_optimal_sequence(
                    requirements=source_code,
                    diagram_output_dir=diagram_dir,
                    criterion_name=criterion,
                    status_slot=status,
                )
                status.update(label="生成完成", state="complete")
            except Exception as exc:
                status.update(label="生成失败", state="error")
                st.error(f"运行失败: {exc}")

    with col_result:
        st.subheader("生成结果")
        result = st.session_state.wb_seq_result

        if result:
            diagram = result["diagram"]
            sequence = result["sequence"]

            # --- State transition diagram ---
            st.markdown("#### 状态转换图")

            tab_diagram_img, tab_diagram_mermaid, tab_diagram_json = st.tabs([
                "状态图", "Mermaid 代码", "JSON",
            ])

            with tab_diagram_img:
                if result["image_path"] and Path(result["image_path"]).exists():
                    st.image(result["image_path"], caption=diagram.title, use_container_width=True)
                else:
                    st.info("未能渲染状态图图片（可能 Graphviz 未安装）。请查看下方 Mermaid 代码。")
                    st.code(result["mermaid_code"], language="mermaid")

            with tab_diagram_mermaid:
                st.code(result["mermaid_code"], language="mermaid")

            with tab_diagram_json:
                st.json(result["diagram_dict"])

            # --- State & transition summary ---
            st.markdown("#### 状态与转换摘要")
            sm1, sm2, sm3 = st.columns(3)
            sm1.metric("状态数", len(diagram.states))
            sm2.metric("转换数", len(diagram.transitions))
            sm3.metric("覆盖准则", result["criterion"])

            # --- Optimal test sequence ---
            st.markdown("#### 最优测试序列")
            st.markdown(f"**序列长度**: {len(sequence.steps)} 步 | **状态路径**: {' → '.join(result['state_sequence'])}")

            # Build table rows
            seq_rows = []
            for step in sequence.steps:
                seq_rows.append({
                    "步骤": step.step,
                    "动作/触发器": step.action,
                    "起始状态": step.from_state,
                    "目标状态": step.to_state,
                    "守卫条件": step.guard if step.guard else "-",
                    "预期结果": step.expected if step.expected else f"进入'{step.to_state}'状态",
                })
            st.dataframe(seq_rows, use_container_width=True, height=360)

            # --- Detailed table ---
            with st.expander("查看详细测试序列表 (Markdown 表格)", expanded=False):
                st.markdown(sequence.to_table())

            # --- JSON export ---
            with st.expander("查看 JSON 导出", expanded=False):
                st.json(json.loads(sequence.to_json()))
        else:
            st.info('上传源代码文件并点击「生成状态图与最优序列」后，结果将显示在这里。')
