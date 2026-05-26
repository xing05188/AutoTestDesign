# AutoTestDesign — AI 驱动的自动化测试设计工具

基于多智能体协作（Multi-Agent Collaboration）的自动化测试设计系统，利用大语言模型（DeepSeek）自动完成需求解析、风险评估、测试用例生成、预期结果合成与测试套件导出。

## 功能特性

- **需求解析** — 支持 CSV、纯文本等多种格式的需求输入，自动提取功能点
- **需求结构化** — 将自然语言需求转化为结构化字段（输入、范围、条件、动作）
- **风险分析** — 基于复杂度、影响范围等因素自动分配风险评分与测试优先级
- **黑盒测试** — 自动生成等价类划分、边界值分析、决策表测试用例
- **白盒测试** — 支持语句覆盖、分支覆盖、条件覆盖、状态转换图建模与测试序列生成
- **Test Oracle 合成** — 自动生成测试预期结果
- **测试套件优化** — 基于风险与覆盖率优化测试套件
- **多格式导出** — 支持 Excel、CSV、JSON 格式导出测试产物
- **可视化仪表盘** — 基于 Streamlit 的交互式 Web UI

## 技术栈

| 层次 | 技术 |
|------|------|
| 多智能体框架 | LangGraph（基于状态机的有向图工作流） |
| LLM 调用 | LangChain + DeepSeek API |
| 前端界面 | Streamlit |
| 数据导出 | openpyxl / pandas / JSON |
| 图形建模 | graphviz / matplotlib |
| 数据验证 | Pydantic |
| 代码覆盖 | Coverage.py / pytest-cov |

## 项目结构

```
AutoTestDesign/
├── main.py                        # Streamlit 简易入口
├── config.py                      # 全局配置
├── requirements.txt               # 依赖清单
├── .env.example                   # 环境变量模板
├── .gitignore
│
├── agents/                        # 智能体模块
│   ├── __init__.py
│   ├── input_parser.py            # 输入解析智能体
│   ├── requirement_structurer.py  # 需求结构化智能体
│   ├── risk_analyzer.py           # 风险分析智能体
│   ├── blackbox_tester.py         # 黑盒测试智能体
│   ├── whitebox_tester.py         # 白盒测试智能体入口
│   ├── oracle_generator.py        # Test Oracle 合成智能体
│   ├── optimizer.py               # 测试套件优化智能体
│   ├── exporter.py                # 导出智能体
│   │
│   └── whitebox/                  # 白盒测试子模块
│       ├── branch_analyzer.py     # 分支覆盖分析
│       ├── condition_analyzer.py  # 条件覆盖分析
│       ├── state_transition.py    # 状态转换图建模
│       ├── statement_qodocover.py # 语句覆盖分析
│       ├── test_generator.py      # 白盒测试生成
│       ├── optimal_sequence.py    # 最优测试序列
│       ├── pipeline.py            # 白盒测试流水线
│       ├── prompt.py              # Prompt 模板
│       └── example_usage.py       # 使用示例
│
├── graph/                         # 工作流编排
│   ├── __init__.py
│   ├── state.py                   # 共享状态定义
│   └── workflow.py                # LangGraph 工作流
│
├── models/                        # 数据模型
│   ├── __init__.py
│   └── schemas.py                 # Pydantic 数据模式
│
├── prompts/                       # Prompt 工程
│   ├── __init__.py
│   └── templates.py               # Prompt 模板
│
├── utils/                         # 工具模块
│   ├── __init__.py
│   ├── llm_client.py              # LLM 客户端封装
│   └── visualizer.py              # 可视化工具
│
├── dashboard/                     # 仪表盘静态资源
│   ├── index.html
│   ├── app.js
│   └── styles.css
│
├── tests/                         # 测试用例
│   ├── test_input_parser.py
│   ├── test_requirement_structurer.py
│   ├── test_risk_analyzer.py
│   ├── test_blackbox_tester.py
│   ├── analyze_risk_results.py
│   └── test_white_box/            # 白盒测试示例
│       ├── ex1/ ...               # 计算器覆盖测试
│       ├── ex2/ ...               # 计算器 BVA/EP 测试
│       ├── ex3/ ...               # 计算器决策表测试
│       ├── ex4/ ...               # 状态转换图示例
│       └── ex5/ ...               # 综合示例
│
└── docs/                          # 文档
    ├── AutoTestDesign_Planning.md # 项目规划文档
    └── Assignment 2.pdf
```

## 快速开始

### 1. 环境准备

确保 Python >= 3.10。

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API Key

复制 `.env.example` 为 `.env`，填写 DeepSeek API Key：

```bash
# .env
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_API_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

### 4. 启动应用

```bash
streamlit run dashboard/app.py
```

浏览器打开 http://localhost:8501 即可使用仪表盘界面。

## 工作流

```
输入需求 → 需求解析 → 需求结构化 → 风险分析
                                    ↓
                      ┌─────────────┼─────────────┐
                      ↓             ↓             ↓
                  黑盒测试      白盒测试    Oracle 合成
                      └─────────────┼─────────────┘
                                    ↓
                              测试套件优化
                                    ↓
                              多格式导出
```

## 许可证

仅供学习与项目演示使用。