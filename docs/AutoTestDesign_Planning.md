# AutoTestDesign 项目规划文档

> **版本**: v1.0  
> **技术栈**: Python · LangChain · LangGraph · Streamlit · DEEPSEEK API  
> **架构模式**: 多智能体协作（Multi-Agent Collaboration）

---

## 一、项目概述

### 1.1 项目目标

开发一款 AI 驱动的自动化测试设计工具 **AutoTestDesign**，通过多智能体协作完成：
- 软件需求的解析与结构化
- 风险评估与优先级分析
- 黑盒/白盒测试用例自动生成
- 测试预期结果（Oracle）合成
- 测试套件优化与导出

### 1.2 技术选型

| 层次 | 技术 | 说明 |
|------|------|------|
| 多智能体框架 | **LangGraph** | 基于状态机的有向图工作流，支持并行/条件路由 |
| LLM 调用 | **LangChain + DEEPSEEK** | deepseek-chat |
| 前端界面 | **Streamlit** | 快速构建交互式 Web UI |
| 数据导出 | **openpyxl / pandas / json** | 支持 Excel、CSV、JSON 导出 |
| 图形建模 | **graphviz / matplotlib** | 状态转换图可视化 |
| 数据验证 | **Pydantic** | 智能体间数据契约 |

---

## 二、需求分析

### 2.1 功能需求（FR）映射到智能体

| 需求 ID | 功能描述 | 负责智能体 |
|---------|---------|-----------|
| FR1.0 | 从 CSV、纯文本、用户输入导入需求 | **InputParserAgent** |
| FR1.1 | 解析并结构化需求（输入字段、范围、条件、动作） | **RequirementStructurerAgent** |
| FR2.0 | 分配风险评分与测试优先级（高/中/低） | **RiskAnalyzerAgent** |
| FR3.0 | 自动生成黑盒测试用例（EP、BVA、决策表） | **BlackBoxTestAgent** |
| FR4.0 | 建模系统行为（状态转换图）并生成测试序列 | **WhiteBoxTestAgent** |
| FR5.0 | 合成给定测试数据的预期结果（Test Oracle） | **TestOracleAgent** |
| FR6.0 | 生成结构化测试产物（JSON/Excel/CSV） | **ExportAgent** |
| FR7.0 | 基于风险/覆盖率优化/最小化测试套件 | **OptimizerAgent** |

### 2.2 非功能需求（NFR）

| NFR | 实现方案 |
|-----|---------|
| **性能** | LangGraph 并行节点（BlackBox + WhiteBox 并发执行），异步 LLM 调用 |
| **可用性（UX/UI）** | Streamlit 多步骤向导式界面，进度条、实时流式输出 |
| **安全性** | API Key 通过 `.env` 文件注入，不硬编码；输入内容过滤 |
| **可维护性** | 模块化代码结构，每个 Agent 独立文件，Pydantic Schema 强类型 |

---

## 三、系统架构设计

### 3.1 总体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     Streamlit UI Layer                       │
│  [文件上传] [文本输入] [配置面板] [结果展示] [导出按钮]          │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│               LangGraph Orchestration Layer                  │
│                                                              │
│   ┌──────────────────────────────────────────────────┐      │
│   │              OrchestratorAgent (路由器)            │      │
│   │   · 接收初始输入                                   │      │
│   │   · 管理工作流状态（SharedState）                  │      │
│   │   · 决策条件路由（conditional edges）              │      │
│   └───────────────────┬──────────────────────────────┘      │
│                       │                                      │
│         ┌─────────────▼───────────────────┐                 │
│         │         工作流节点图              │                 │
│         │                                 │                 │
│  ┌──────▼──────┐  ┌──────────────────┐   │                 │
│  │ InputParser  │→│  ReqStructurer   │   │                 │
│  │   Agent      │  │     Agent        │   │                 │
│  └─────────────┘  └────────┬─────────┘   │                 │
│                             │             │                 │
│                    ┌────────▼─────────┐   │                 │
│                    │  RiskAnalyzer    │   │                 │
│                    │     Agent        │   │                 │
│                    └────────┬─────────┘   │                 │
│                             │             │                 │
│              ┌──────────────┼──────────┐  │                 │
│              │              │          │  │                 │
│     ┌────────▼───┐  ┌───────▼──────┐  │  │                 │
│     │  BlackBox  │  │  WhiteBox    │  │  │                 │
│     │ TestAgent  │  │  TestAgent   │  │  │                 │
│     └────────┬───┘  └───────┬──────┘  │  │                 │
│              └──────┬───────┘         │  │                 │
│                     │                 │  │                 │
│            ┌────────▼──────┐          │  │                 │
│            │  TestOracle   │          │  │                 │
│            │    Agent      │          │  │                 │
│            └────────┬──────┘          │  │                 │
│                     │                 │  │                 │
│            ┌────────▼──────┐          │  │                 │
│            │  Optimizer    │          │  │                 │
│            │    Agent      │          │  │                 │
│            └────────┬──────┘          │  │                 │
│                     │                 │  │                 │
│            ┌────────▼──────┐          │  │                 │
│            │  Export       │          │  │                 │
│            │    Agent      │          │  │                 │
│            └───────────────┘          │  │                 │
│         └───────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                    LLM Layer (Claude API)                    │
│   · 所有 Agent 共享 LLM 实例                                  │
│   · 每个 Agent 拥有专属 System Prompt                         │
│   · 支持流式输出（streaming）                                  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 LangGraph 状态机定义

**SharedState（共享状态，贯穿整个工作流）：**

```python
class AutoTestState(TypedDict):
    # 输入
    raw_input: str                          # 原始需求文本
    input_format: str                       # "csv" | "text" | "manual"
    
    # FR1.0 / FR1.1 输出
    parsed_requirements: List[Requirement]  # 解析后的需求列表
    
    # FR2.0 输出
    risk_analysis: List[RiskItem]           # 风险分析结果
    
    # FR3.0 输出
    blackbox_tests: List[TestCase]          # 黑盒测试用例
    
    # FR4.0 输出
    whitebox_tests: List[TestCase]          # 白盒测试用例
    state_diagram: str                      # 状态转换图（DOT 格式）
    
    # FR5.0 输出
    enriched_tests: List[TestCase]          # 含 Oracle 的测试用例
    
    # FR7.0 输出
    optimized_suite: List[TestCase]         # 优化后的测试套件
    
    # FR6.0 输出
    export_artifacts: Dict[str, Any]        # 导出产物路径
    
    # 工作流控制
    current_step: str
    errors: List[str]
    messages: List[BaseMessage]             # LLM 对话历史
```

---

## 四、各智能体详细设计

### 4.1 InputParserAgent（输入解析智能体）

**职责**：接收多格式输入，统一转换为内部需求表示

**输入**：原始文本 / CSV 文件内容 / 用户手动输入

**输出**：`List[RawRequirement]`

**核心逻辑**：
```
1. 检测输入格式（CSV 头检测 / 纯文本判断）
2. CSV → pandas 解析 → 逐行提取
3. 纯文本 → 按需求 ID 模式分割 / LLM 辅助切分
4. 构造统一的 RawRequirement 对象列表
```

**System Prompt 设计**：
```
你是一个需求解析专家。给定用户输入的软件需求文档（可能是纯文本、CSV或格式化列表），
请提取所有独立的需求条目，每条需求包含：
- requirement_id: 需求唯一标识
- title: 需求标题
- description: 详细描述
- source: 来源（原始文本片段）

以 JSON 数组格式返回，不要包含任何其他文字。
```

---

### 4.2 RequirementStructurerAgent（需求结构化智能体）

**职责**：深度解析每条需求，提取可测试的结构化元素

**输入**：`List[RawRequirement]`

**输出**：`List[Requirement]`（含 input_fields, data_ranges, conditions, expected_actions）

**数据结构**：
```python
class Requirement(BaseModel):
    req_id: str
    title: str
    description: str
    input_fields: List[InputField]      # e.g., [{"name": "age", "type": "integer"}]
    data_ranges: List[DataRange]        # e.g., [{"field": "age", "min": 0, "max": 120}]
    conditions: List[str]               # e.g., ["if age < 18", "if age >= 65"]
    expected_actions: List[str]         # e.g., ["show error message", "grant access"]
    domain: str                         # 需求领域（登录/支付/搜索等）
```

**System Prompt 设计**：
```
你是一个软件测试分析专家，精通 ISTQB 测试基础知识。
对于给定的软件需求，请识别并提取以下测试相关元素：
1. 输入字段（名称、数据类型、约束）
2. 数据范围（最小值、最大值、有效值集合）
3. 业务条件（if/when 条件语句）
4. 预期行为（系统应执行的动作）

严格按照指定 JSON Schema 返回，不要添加额外解释。
```

---

### 4.3 RiskAnalyzerAgent（风险分析智能体）

**职责**：基于需求复杂度、业务重要性、变更频率等维度计算风险评分

**输入**：`List[Requirement]`

**输出**：`List[RiskItem]`

**风险评分模型**：
```
风险分数 = (影响度 × 0.4) + (发生概率 × 0.35) + (复杂度 × 0.25)
优先级映射：
  High:   风险分数 ≥ 7
  Medium: 风险分数 ∈ [4, 7)
  Low:    风险分数 < 4
```

**数据结构**：
```python
class RiskItem(BaseModel):
    req_id: str
    impact: int               # 1-10：对业务的影响程度
    probability: int          # 1-10：缺陷发生概率
    complexity: int           # 1-10：实现复杂度
    risk_score: float         # 综合风险分
    priority: str             # "High" | "Medium" | "Low"
    risk_factors: List[str]   # 风险因素描述
    mitigation: str           # 风险缓解建议
```

**System Prompt 设计**：
```
你是一个软件风险评估专家，遵循 ISO/IEC/IEEE 29119 标准。
对于每个软件需求，请评估：
1. 业务影响度（1-10）：该需求失败对业务的影响程度
2. 缺陷概率（1-10）：该需求中存在缺陷的可能性（考虑复杂度、歧义性）
3. 实现复杂度（1-10）：技术实现的难度
4. 主要风险因素列表
5. 风险缓解建议

返回指定格式的 JSON 数组。
```

---

### 4.4 BlackBoxTestAgent（黑盒测试智能体）

**职责**：自动应用三种核心黑盒技术生成测试用例

**支持技术**：
1. **等价类划分（Equivalence Partitioning, EP）**
2. **边界值分析（Boundary Value Analysis, BVA）**
3. **决策表（Decision Table）**

**输入**：`List[Requirement]`（含结构化信息）

**输出**：`List[TestCase]`（黑盒测试用例）

**每种技术的 Prompt 策略**：

**EP Prompt**：
```
基于等价类划分技术（ISO/IEC/IEEE 29119-4），对以下需求生成测试用例：
- 识别有效等价类和无效等价类
- 每个等价类至少生成一个测试用例
- 为每个测试用例提供：ID、名称、等价类描述、测试输入、预期行为类型
```

**BVA Prompt**：
```
基于边界值分析技术，对以下需求的每个数值范围生成边界测试用例：
- 边界点：最小值、最小值+1、最大值-1、最大值
- 扩展边界：最小值-1（无效）、最大值+1（无效）
- 包括：正常边界、异常边界（超出范围）
```

**决策表 Prompt**：
```
基于决策表技术，对以下需求的多条件组合生成测试用例：
1. 列出所有条件（Conditions）
2. 列出所有动作（Actions）
3. 枚举有意义的条件组合规则
4. 为每条规则生成测试用例
```

**数据结构**：
```python
class TestCase(BaseModel):
    tc_id: str
    req_id: str
    technique: str          # "EP" | "BVA" | "Decision_Table" | "State_Transition"
    title: str
    description: str
    preconditions: List[str]
    test_steps: List[TestStep]
    test_data: Dict[str, Any]
    expected_result: str
    priority: str
    is_positive: bool       # 正向/负向测试用例
```

---

### 4.5 WhiteBoxTestAgent（白盒测试智能体）

**职责**：建模系统状态行为，生成最优测试序列

**核心技术**：**状态转换图（State Transition Diagram）**

**输入**：`List[Requirement]`

**输出**：
- `List[TestCase]`（白盒测试用例序列）
- `str`（DOT 格式状态图，可视化用）

**工作流程**：
```
1. LLM 分析需求，识别系统状态（States）
2. LLM 识别状态转换条件（Events/Triggers）
3. 生成状态转换矩阵（State Transition Table）
4. 基于"全状态覆盖"准则生成最优测试序列
5. 生成 Graphviz DOT 格式图形
```

**System Prompt 设计**：
```
你是白盒测试专家，精通状态转换测试技术（ISO 29119-4 Section 5.4）。
对于给定需求，请：
1. 识别系统所有可能的状态（初始态、中间态、终止态）
2. 识别所有状态转换事件和触发条件
3. 构建状态转换矩阵（State × Event → Next_State × Action）
4. 基于 All-States 覆盖准则设计最优测试序列
5. 返回：状态列表、转换列表、测试序列、DOT图形语法

以指定 JSON 格式返回所有内容。
```

---

### 4.6 TestOracleAgent（测试 Oracle 智能体）

**职责**：为每个测试用例合成精确的预期结果

**输入**：`List[TestCase]`（来自黑盒+白盒）

**输出**：`List[TestCase]`（enriched，含精确 expected_result）

**Oracle 生成策略**：
```
1. 参考原始需求描述
2. 结合测试数据和步骤
3. 基于业务规则推导预期输出
4. 区分功能 Oracle（返回值/UI 状态）和异常 Oracle（错误消息）
```

**System Prompt**：
```
你是测试 Oracle 专家。给定测试用例的输入数据、步骤和原始需求，
请推导并合成精确的预期测试结果，包括：
- 系统的精确输出或行为
- 界面状态变化
- 数据库/系统状态变化（如适用）
- 异常时的错误信息格式
每个 Oracle 应该可验证且明确，不含歧义。
```

---

### 4.7 OptimizerAgent（测试套件优化智能体）

**职责**：基于风险和覆盖率对测试套件进行优先级排序和最小化

**输入**：
- `List[TestCase]`（所有测试用例）
- `List[RiskItem]`（风险信息）

**输出**：`List[TestCase]`（优化排序后的测试套件）

**优化策略**：
```
优先级排序：
1. 风险 High 需求的测试用例 → 排前
2. 核心功能路径（Happy Path）→ 排前
3. 边界和异常用例 → 中等优先级
4. 冗余用例合并/删除

最小化算法：
- 计算需求覆盖率矩阵
- 贪心算法：选择覆盖未覆盖需求最多的测试用例
- 直到满足最低覆盖率要求（默认 80%）
```

---

### 4.8 ExportAgent（导出智能体）

**职责**：将测试产物序列化为标准格式文件

**支持格式**：
- JSON（完整测试套件）
- Excel/XLSX（测试用例表格）
- CSV（轻量导出）

**Excel 结构**：
```
Sheet 1: 需求分析
  - 需求ID | 标题 | 描述 | 输入字段 | 数据范围

Sheet 2: 风险分析报告
  - 需求ID | 影响度 | 概率 | 复杂度 | 风险分 | 优先级 | 风险因素

Sheet 3: 测试用例（黑盒）
  - TC_ID | 需求ID | 技术 | 标题 | 前置条件 | 步骤 | 测试数据 | 预期结果 | 优先级

Sheet 4: 测试用例（白盒）
  - 同上，额外含 状态路径 列

Sheet 5: 优化后测试套件
  - 优先级排序后的完整测试套件
```

---

## 五、项目目录结构

```
autotestdesign/
├── README.md                     # 项目说明
├── requirements.txt              # 依赖清单
├── .env.example                  # 环境变量模板
├── config.py                     # 全局配置
│
├── main.py                       # Streamlit 主入口
│
├── graph/
│   ├── __init__.py
│   ├── state.py                  # SharedState 定义（TypedDict）
│   └── workflow.py               # LangGraph 图构建与编译
│
├── agents/
│   ├── __init__.py
│   ├── input_parser.py           # FR1.0
│   ├── requirement_structurer.py # FR1.1
│   ├── risk_analyzer.py          # FR2.0
│   ├── blackbox_tester.py        # FR3.0
│   ├── whitebox_tester.py        # FR4.0
│   ├── oracle_generator.py       # FR5.0
│   ├── optimizer.py              # FR7.0
│   └── exporter.py               # FR6.0
│
├── models/
│   ├── __init__.py
│   └── schemas.py                # Pydantic 数据模型
│
├── utils/
│   ├── __init__.py
│   ├── llm_client.py             # Claude API 封装
│   ├── csv_handler.py            # CSV 解析工具
│   └── visualizer.py            # 状态图可视化
│
├── prompts/
│   ├── __init__.py
│   └── templates.py             # 所有 Agent 的 Prompt 模板
│
├── outputs/                      # 生成的测试产物
│   └── .gitkeep
│
└── tests/
    ├── sample_requirements.csv   # 示例需求文件
    └── sample_requirements.txt  # 示例纯文本需求
```

---

## 六、LangGraph 工作流详细设计

### 6.1 节点（Nodes）定义

```python
# workflow.py 伪代码
from langgraph.graph import StateGraph, END

builder = StateGraph(AutoTestState)

# 注册节点
builder.add_node("parse_input",        input_parser_node)
builder.add_node("structure_reqs",     req_structurer_node)
builder.add_node("analyze_risk",       risk_analyzer_node)
builder.add_node("generate_blackbox",  blackbox_node)
builder.add_node("generate_whitebox",  whitebox_node)
builder.add_node("generate_oracle",    oracle_node)
builder.add_node("optimize_suite",     optimizer_node)
builder.add_node("export_artifacts",   export_node)

# 设置入口
builder.set_entry_point("parse_input")
```

### 6.2 边（Edges）与路由

```python
# 顺序边
builder.add_edge("parse_input",       "structure_reqs")
builder.add_edge("structure_reqs",    "analyze_risk")

# 并行分叉（黑盒+白盒同时执行）
builder.add_edge("analyze_risk",      "generate_blackbox")
builder.add_edge("analyze_risk",      "generate_whitebox")

# 汇合后继续
builder.add_edge("generate_blackbox", "generate_oracle")
builder.add_edge("generate_whitebox", "generate_oracle")

builder.add_edge("generate_oracle",   "optimize_suite")
builder.add_edge("optimize_suite",    "export_artifacts")
builder.add_edge("export_artifacts",  END)

# 条件路由（错误处理）
builder.add_conditional_edges(
    "parse_input",
    route_after_parsing,   # 检查 state.errors
    {"continue": "structure_reqs", "error": END}
)
```

### 6.3 并行节点实现

LangGraph 支持通过 `Send` API 或分叉写入同一 State key 实现并行：

```python
# 黑盒和白盒节点都写入各自的 state key
# LangGraph 检测到两个节点都从 analyze_risk 出发时自动并行
```

---

## 七、数据流向图

```
用户输入（CSV/Text/Manual）
        │
        ▼
InputParserAgent ──────────────────────► parsed_requirements[]
        │
        ▼
RequirementStructurerAgent ─────────────► structured_requirements[]
  (提取: input_fields, ranges,             (Pydantic Requirement 对象)
   conditions, expected_actions)
        │
        ▼
RiskAnalyzerAgent ──────────────────────► risk_analysis[]
  (计算: risk_score, priority,              (RiskItem 对象)
   risk_factors, mitigation)
        │
        ├──────────────────────────────┐
        ▼                              ▼
BlackBoxTestAgent              WhiteBoxTestAgent
  · EP (等价类)                  · 状态转换图
  · BVA (边界值)                 · 全状态覆盖序列
  · Decision Table               · DOT 图形
        │                              │
        └──────────────────────────────┘
                       │
                       ▼
             TestOracleAgent ───────────► enriched_tests[]
               (合成每个 TC 的              (含精确 expected_result)
                预期结果 Oracle)
                       │
                       ▼
             OptimizerAgent ────────────► optimized_suite[]
               (优先级排序 +               (最终测试套件)
                冗余删除)
                       │
                       ▼
             ExportAgent ───────────────► outputs/
               · test_suite.json           (JSON/Excel/CSV)
               · test_cases.xlsx
               · risk_report.csv
```

---

## 八、实现计划

### Phase 1：基础框架搭建（核心骨架）
1. 创建项目目录结构
2. 定义 Pydantic Schema（`models/schemas.py`）
3. 实现 LLM 客户端封装（`utils/llm_client.py`）
4. 定义 SharedState（`graph/state.py`）
5. 编写所有 Prompt 模板（`prompts/templates.py`）

### Phase 2：各 Agent 实现
1. InputParserAgent
2. RequirementStructurerAgent
3. RiskAnalyzerAgent
4. BlackBoxTestAgent（EP + BVA + Decision Table）
5. WhiteBoxTestAgent（State Transition）
6. TestOracleAgent
7. OptimizerAgent
8. ExportAgent

### Phase 3：LangGraph 工作流集成
1. 构建 StateGraph（`graph/workflow.py`）
2. 注册所有节点和边
3. 实现错误处理和条件路由
4. 端到端测试

### Phase 4：Streamlit UI
1. 文件上传 / 文本输入界面
2. 实时流式进度展示
3. 结果可视化（状态图、测试用例表格、风险报告）
4. 导出按钮

---

## 九、关键技术实现细节

### 9.1 LLM 结构化输出

所有 Agent 使用 `with_structured_output()` 或 JSON 模式确保输出可解析：

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser

llm = ChatAnthropic(model="deepseek-chat")
parser = JsonOutputParser(pydantic_object=Requirement)
chain = prompt | llm | parser
```

### 9.2 Agent 错误处理

```python
def safe_agent_call(agent_func, state, fallback):
    try:
        return agent_func(state)
    except Exception as e:
        state["errors"].append(f"{agent_func.__name__}: {str(e)}")
        return fallback
```

### 9.3 进度回调（Streamlit 集成）

```python
# 使用 LangGraph 的 stream 模式
for event in graph.stream(initial_state):
    node_name = list(event.keys())[0]
    update_progress_bar(node_name)
    display_partial_results(event[node_name])
```

---

## 十、示例需求文件

**sample_requirements.csv**：
```csv
req_id,title,description
REQ-001,用户登录,用户使用用户名(4-20字符)和密码(8-16字符,含大写字母和数字)登录。失败3次后锁定账户。
REQ-002,年龄验证,系统验证用户年龄。年龄必须在0-120之间。18岁以下显示"未成年"，18-65显示"成年"，65岁以上显示"老年"。
REQ-003,购物车结算,用户可添加商品到购物车(最多50件)，总金额超过100元免运费，否则收取10元运费。
REQ-004,密码重置,用户通过邮件重置密码。重置链接24小时内有效，点击后进入密码修改页面。
```

---
