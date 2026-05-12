"""
AutoTestDesign - Pydantic 数据模型定义
所有智能体之间传递的数据结构
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


# ─────────────────────────────────────────────
# 枚举类型
# ─────────────────────────────────────────────

class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class TestTechnique(str, Enum):
    EP = "Equivalence_Partitioning"
    BVA = "Boundary_Value_Analysis"
    DECISION_TABLE = "Decision_Table"
    STATE_TRANSITION = "State_Transition"


# ─────────────────────────────────────────────
# FR1.0 / FR1.1 - 需求解析结果
# ─────────────────────────────────────────────

class InputField(BaseModel):
    name: str = Field(description="字段名称")
    data_type: str = Field(description="数据类型: string/integer/float/boolean/date/enum")
    description: str = Field(default="", description="字段描述")
    constraints: List[str] = Field(default_factory=list, description="约束条件列表")


class DataRange(BaseModel):
    field_name: str = Field(description="字段名称")
    min_value: Optional[str] = Field(default=None, description="最小值")
    max_value: Optional[str] = Field(default=None, description="最大值")
    valid_values: List[str] = Field(default_factory=list, description="有效值枚举")
    invalid_values: List[str] = Field(default_factory=list, description="无效值示例")


class Requirement(BaseModel):
    req_id: str = Field(description="需求唯一标识")
    title: str = Field(description="需求标题")
    description: str = Field(description="需求详细描述")
    input_fields: List[InputField] = Field(default_factory=list)
    data_ranges: List[DataRange] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list, description="业务条件列表")
    expected_actions: List[str] = Field(default_factory=list, description="预期系统行为")
    domain: str = Field(default="general", description="需求领域")


# ─────────────────────────────────────────────
# FR2.0 - 风险分析结果
# ─────────────────────────────────────────────

class RiskItem(BaseModel):
    req_id: str
    title: str = Field(default="")
    impact: int = Field(ge=1, le=10, description="业务影响度 1-10")
    probability: int = Field(ge=1, le=10, description="缺陷发生概率 1-10")
    complexity: int = Field(ge=1, le=10, description="实现复杂度 1-10")
    risk_score: float = Field(description="综合风险分 = impact*0.4 + prob*0.35 + complex*0.25")
    priority: Priority = Field(description="测试优先级")
    risk_factors: List[str] = Field(default_factory=list, description="风险因素")
    mitigation: str = Field(default="", description="缓解建议")


# ─────────────────────────────────────────────
# FR3.0 / FR4.0 / FR5.0 - 测试用例
# ─────────────────────────────────────────────

class TestStep(BaseModel):
    step_number: int
    action: str = Field(description="操作描述")
    expected: str = Field(default="", description="该步骤的预期结果")


class EquivalenceClass(BaseModel):
    class_id: str
    field_name: str
    class_type: str = Field(description="valid/invalid")
    description: str
    representative_value: str


class BoundaryPoint(BaseModel):
    field_name: str
    boundary_type: str = Field(description="min/min+1/max-1/max/below_min/above_max")
    value: str
    is_valid: bool


class DecisionRule(BaseModel):
    rule_id: str
    conditions: Dict[str, str] = Field(description="条件取值映射")
    actions: List[str] = Field(description="触发的动作")


class TestCase(BaseModel):
    tc_id: str
    req_id: str
    technique: TestTechnique
    title: str
    description: str = Field(default="")
    preconditions: List[str] = Field(default_factory=list)
    test_steps: List[TestStep] = Field(default_factory=list)
    test_data: Dict[str, Any] = Field(default_factory=dict)
    expected_result: str = Field(default="")
    priority: Priority = Field(default=Priority.MEDIUM)
    is_positive: bool = Field(default=True, description="正向/负向测试")
    coverage_tags: List[str] = Field(default_factory=list, description="覆盖的等价类/边界/规则")


# ─────────────────────────────────────────────
# FR4.0 - 白盒/状态转换模型
# ─────────────────────────────────────────────

class State(BaseModel):
    state_id: str
    name: str
    description: str = ""
    is_initial: bool = False
    is_final: bool = False


class Transition(BaseModel):
    from_state: str
    event: str
    condition: str = ""
    to_state: str
    action: str = ""


class StateTransitionModel(BaseModel):
    req_id: str
    states: List[State]
    transitions: List[Transition]
    dot_graph: str = Field(default="", description="Graphviz DOT 格式图形")


# ─────────────────────────────────────────────
# FR6.0 - 导出产物
# ─────────────────────────────────────────────

class ExportArtifact(BaseModel):
    json_path: str = ""
    excel_path: str = ""
    csv_path: str = ""
    summary: Dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# FR7.0 - 优化结果
# ─────────────────────────────────────────────

class OptimizationResult(BaseModel):
    original_count: int
    optimized_count: int
    coverage_rate: float
    removed_ids: List[str] = Field(default_factory=list)
    reasoning: str = ""
