"""
AutoTestDesign - 全局配置
"""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent

# 输出目录
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# 默认配置
DEFAULT_CONFIG = {
    "risk_threshold_high": 7.0,
    "risk_threshold_medium": 4.0,
    "min_coverage_rate": 0.8,
    "max_test_cases": 150,
    "enable_ep": True,
    "enable_bva": True,
    "enable_decision_table": True,
    "enable_state_transition": True,
    "batch_size_structuring": 5,
    "batch_size_risk": 8,
    "batch_size_oracle": 10,
}

# 示例需求
SAMPLE_REQUIREMENTS_CSV = """req_id,title,description
REQ-001,用户登录,用户使用用户名（4-20个字符，只允许字母数字下划线）和密码（8-16个字符，必须包含大写字母和数字）进行登录。连续登录失败3次后锁定账户30分钟。
REQ-002,年龄分类,系统根据用户输入的年龄（整数，范围0-150）进行分类：0-17岁显示"未成年人"，18-64岁显示"成年人"，65岁及以上显示"老年人"，超出范围显示错误。
REQ-003,购物车结算,用户可以将商品加入购物车（每种商品最多99件，购物车最多50种商品）。订单总金额满100元免运费，不满则收取10元运费，总金额超过1000元享受9折优惠。
REQ-004,密码重置,用户通过注册邮箱申请重置密码。系统发送含重置链接的邮件，链接24小时内有效。点击链接后进入密码修改页面，新密码须符合密码规则且不能与最近3次历史密码相同."""

SAMPLE_REQUIREMENTS_TEXT = """
需求1：用户注册
用户可以使用邮箱地址注册账号。邮箱必须符合标准格式（xxx@xxx.xxx）。
用户名长度3-20个字符，只能包含字母、数字和下划线。
密码长度8-20个字符，至少包含一个大写字母、一个小写字母和一个数字。
注册时需要确认密码，两次输入必须一致。注册成功后发送验证邮件。

需求2：商品搜索
用户可以通过关键词搜索商品。搜索关键词长度1-50个字符。
系统返回匹配的商品列表，按相关度排序。
支持按价格区间筛选（最低价格0元，最高价格不限）。
每页显示20个结果，支持翻页。无结果时显示"未找到相关商品"。
"""
