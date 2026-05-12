"""Streamlit UI - AutoTestDesign 简易入口
提供文本输入、运行工作流并展示进度与导出结果（最小实现）。
"""

import streamlit as st
from config import SAMPLE_REQUIREMENTS_TEXT, DEFAULT_CONFIG
from graph.state import create_initial_state
from agents.input_parser import input_parser_node
from agents.requirement_structurer import requirement_structurer_node
from agents.risk_analyzer import risk_analyzer_node
from agents.blackbox_tester import blackbox_tester_node
from agents.whitebox_tester import whitebox_tester_node
from agents.oracle_generator import oracle_generator_node
from agents.optimizer import optimizer_node
from agents.exporter import exporter_node


st.set_page_config(page_title="AutoTestDesign", layout="wide")

st.title("AutoTestDesign — 自动测试设计 (演示版)")

with st.sidebar:
    st.header("配置")
    config = DEFAULT_CONFIG.copy()
    config["min_coverage_rate"] = st.sidebar.slider("最小覆盖率", 0.1, 1.0, 0.8)
    config["enable_state_transition"] = st.sidebar.checkbox("启用状态转换", True)
    config["enable_bva"] = st.sidebar.checkbox("启用边界值分析", True)

input_text = st.text_area("粘贴需求文本（或使用示例）", value=SAMPLE_REQUIREMENTS_TEXT, height=300)

if st.button("运行工作流"):
    state = create_initial_state(raw_input=input_text, input_format="auto", config=config)

    # 1. 解析
    out = input_parser_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        st.info(msg)

    # 2. 结构化
    out = requirement_structurer_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        st.info(msg)

    # 3. 风险评估
    out = risk_analyzer_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        st.info(msg)

    # 4. 黑盒 & 白盒（并行模拟）
    out_bb = blackbox_tester_node(state)
    out_wb = whitebox_tester_node(state)
    state.update(out_bb)
    state.update(out_wb)
    for msg in out_bb.get("progress_messages", []) + out_wb.get("progress_messages", []):
        st.info(msg)

    # 5. 合并并生成 Oracle
    merged = {
        "blackbox_tests": state.get("blackbox_tests", []),
        "whitebox_tests": state.get("whitebox_tests", []),
    }
    out = oracle_generator_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        st.info(msg)

    # 6. 优化
    out = optimizer_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        st.info(msg)

    # 7. 导出
    out = exporter_node(state)
    state.update(out)
    for msg in out.get("progress_messages", []):
        st.success(msg)

    st.write("导出产物：", out.get("export_artifact", {}))

    st.balloons()
