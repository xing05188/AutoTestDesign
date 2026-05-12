"""
AutoTestDesign - 可视化工具
渲染状态转换图为图片
"""

import re
from typing import Optional


def dot_to_mermaid(dot_graph: str) -> str:
    """
    将 Graphviz DOT 格式转换为 Mermaid 格式
    用于在 Streamlit 中展示（无需安装 graphviz 二进制）
    """
    if not dot_graph:
        return "graph LR\n    A[无状态图]"

    lines = dot_graph.strip().split('\n')
    mermaid_lines = ["stateDiagram-v2"]

    for line in lines:
        line = line.strip()
        if not line or line in ('{', '}') or line.startswith('digraph') or line.startswith('rankdir'):
            continue

        # 解析节点定义: S0 [label="状态名" ...]
        node_match = re.match(r'(\w+)\s*\[.*?label="([^"]*)".*?\]', line)
        if node_match:
            state_id = node_match.group(1)
            label = node_match.group(2)
            mermaid_lines.append(f'    {state_id}: {label}')
            continue

        # 解析边定义: S0 -> S1 [label="事件"]
        edge_match = re.match(r'(\w+)\s*->\s*(\w+)\s*(?:\[.*?label="([^\"]*)".*?\])?', line)
        if edge_match:
            from_state = edge_match.group(1)
            to_state = edge_match.group(2)
            label = edge_match.group(3) or ""
            if label:
                mermaid_lines.append(f'    {from_state} --> {to_state}: {label}')
            else:
                mermaid_lines.append(f'    {from_state} --> {to_state}')

    return '\n'.join(mermaid_lines)


def generate_simple_dot(states: list, transitions: list) -> str:
    """从状态和转换列表生成 DOT 图形"""
    lines = ["digraph G {", "  rankdir=LR;", "  node [fontname=\"Arial\"];"]

    for state in states:
        state_id = state.get("state_id", "S?")
        name = state.get("name", state_id)
        is_initial = state.get("is_initial", False)
        is_final = state.get("is_final", False)

        attrs = [f'label="{name}"']
        if is_initial:
            attrs.append('style=filled fillcolor=lightblue')
        if is_final:
            attrs.append('shape=doublecircle')
        else:
            attrs.append('shape=circle')

        lines.append(f'  {state_id} [{" ".join(attrs)}];')

    for trans in transitions:
        from_s = trans.get("from_state", "")
        to_s = trans.get("to_state", "")
        event = trans.get("event", "")
        condition = trans.get("condition", "")

        label = event
        if condition:
            label = f"{event}\\n[{condition}]"

        lines.append(f'  {from_s} -> {to_s} [label="{label}"];')

    lines.append("}")
    return "\n".join(lines)


def create_workflow_diagram() -> str:
    """生成工作流架构图（Mermaid 格式）"""
    return """graph TD
    A[📥 用户输入<br/>CSV/文本/手动] --> B[InputParser<br/>需求解析 Agent]
    B --> C{解析成功?}
    C -->|是| D[ReqStructurer<br/>需求结构化 Agent]
    C -->|否| Z[❌ 终止]
    D --> E{结构化成功?}
    E -->|是| F[RiskAnalyzer<br/>风险分析 Agent]
    E -->|否| Z
    F --> G[BlackBox Test<br/>黑盒测试 Agent]
    F --> H[WhiteBox Test<br/>白盒测试 Agent]
    G --> I[Merge<br/>结果汇合]
    H --> I
    I --> J[TestOracle<br/>预期结果 Agent]
    J --> K[Optimizer<br/>测试优化 Agent]
    K --> L[Exporter<br/>导出 Agent]
    L --> M[📤 输出产物<br/>JSON/Excel/CSV]

    style A fill:#4472C4,color:#fff
    style M fill:#375623,color:#fff
    style Z fill:#C00000,color:#fff
    style F fill:#FF6B35,color:#fff
    style G fill:#2E86AB,color:#fff
    style H fill:#7030A0,color:#fff"""
