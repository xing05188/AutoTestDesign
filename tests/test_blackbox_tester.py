"""
Test BlackBoxTesterAgent
集成测试：InputParser → RequirementStructurer → RiskAnalyzer → BlackBoxTester
验证三种黑盒测试技术（EP、BVA、Decision Table）的测试用例生成
"""

import json
import os
import sys
from datetime import datetime
from collections import Counter

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from agents.input_parser import input_parser_node
from agents.requirement_structurer import requirement_structurer_node
from agents.risk_analyzer import risk_analyzer_node
from agents.blackbox_tester import blackbox_tester_node
from graph.state import create_initial_state


def test_blackbox_tester_pipeline():
    """
    完整流程测试：
    1. InputParserAgent → 解析需求
    2. RequirementStructurerAgent → 结构化分析
    3. RiskAnalyzerAgent → 风险评估
    4. BlackBoxTesterAgent → 生成黑盒测试用例
    """
    print("\n" + "="*70)
    print("TEST: BlackBoxTesterAgent - Complete Pipeline")
    print("="*70)
    
    # 使用文本格式需求输入（tests/requirements_test.txt）进行测试
    input_file = os.path.join(project_root, "tests", "requirements_test.txt")

    with open(input_file, "r", encoding="utf-8") as f:
        raw_content = f.read()

    print(f"📄 Input file: {input_file}")
    print(f"📊 File size: {len(raw_content)} bytes\n")
    
    # Step 1: InputParser
    print("Step 1: InputParserAgent 解析需求...")
    state = create_initial_state(raw_input=raw_content, input_format="auto")
    parse_output = input_parser_node(state)
    parsed_reqs = parse_output.get("parsed_requirements", [])
    print(f"✓ 解析完成：{len(parsed_reqs)} 条需求\n")
    
    # Step 2: RequirementStructurer
    print("Step 2: RequirementStructurerAgent 深度结构化分析...")
    state.update(parse_output)
    struct_output = requirement_structurer_node(state)
    structured_reqs = struct_output.get("structured_requirements", [])
    print(f"✓ 结构化完成：{len(structured_reqs)} 条需求\n")
    
    # Step 3: RiskAnalyzer
    print("Step 3: RiskAnalyzerAgent 风险评估...")
    state.update(struct_output)
    risk_output = risk_analyzer_node(state)
    risk_analysis = risk_output.get("risk_analysis", [])
    print(f"✓ 风险评估完成：{len(risk_analysis)} 条评分\n")
    
    # Step 4: BlackBoxTester
    print("Step 4: BlackBoxTesterAgent 生成黑盒测试用例...")
    state.update(risk_output)
    bb_output = blackbox_tester_node(state)
    blackbox_tests = bb_output.get("blackbox_tests", [])
    print(f"✓ 生成完成：{len(blackbox_tests)} 个测试用例\n")
    
    if bb_output.get("errors"):
        print(f"⚠ 警告: {bb_output.get('errors')}")
    
    # 统计分析
    print("📊 测试用例统计：")
    print("-"*70)
    
    # 按测试技术分类
    technique_dist = Counter()
    priority_dist = {"High": 0, "Medium": 0, "Low": 0}
    req_dist = Counter()
    
    for test in blackbox_tests:
        technique = test.get("technique", "Unknown")
        priority = test.get("priority", "Medium")
        req_id = test.get("req_id", "UNKNOWN")
        
        technique_dist[technique] += 1
        if priority in priority_dist:
            priority_dist[priority] += 1
        req_dist[req_id] += 1
    
    print("\n按测试技术分布：")
    for technique, count in technique_dist.most_common():
        print(f"  • {technique:30} {count:3} 个")
    
    print("\n按优先级分布：")
    for priority in ["High", "Medium", "Low"]:
        count = priority_dist[priority]
        icon = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(priority, "⚪")
        print(f"  {icon} {priority:10} {count:3} 个")
    
    print("\n按需求分布：")
    for req_id, count in sorted(req_dist.items()):
        print(f"  • {req_id:10} {count:3} 个用例")
    
    # 显示高风险需求的测试覆盖
    print("\n🔴 高风险需求的测试覆盖：")
    print("-"*70)
    
    high_risk_reqs = {r.get("req_id"): r for r in risk_analysis if r.get("priority") == "High"}
    
    for req_id, risk_info in high_risk_reqs.items():
        req_tests = [t for t in blackbox_tests if t.get("req_id") == req_id]
        req_techniques = Counter(t.get("technique") for t in req_tests)
        
        print(f"\n{req_id}: {risk_info.get('title')}")
        print(f"  风险分: {risk_info.get('risk_score')} | {len(req_tests)} 个测试用例")
        print(f"  技术组合:", end="")
        for technique, count in req_techniques.most_common():
            print(f" {technique}={count}", end=" ")
        print()
        
        # 显示前 3 个测试用例
        print(f"  示例用例:")
        for i, test in enumerate(req_tests[:3], 1):
            print(f"    [{i}] {test.get('tc_id'):15} | {test.get('title')[:45]}")
    
    # 测试用例质量指标
    print("\n📈 测试用例质量指标：")
    print("-"*70)
    
    total_steps = sum(len(t.get("test_steps", [])) for t in blackbox_tests)
    avg_steps = total_steps / len(blackbox_tests) if blackbox_tests else 0
    
    with_data = sum(1 for t in blackbox_tests if t.get("test_data"))
    with_precond = sum(1 for t in blackbox_tests if t.get("preconditions"))
    
    print(f"  • 总测试步骤数: {total_steps}")
    print(f"  • 平均步骤/用例: {avg_steps:.1f}")
    print(f"  • 包含测试数据的用例: {with_data}/{len(blackbox_tests)} ({with_data/len(blackbox_tests)*100:.1f}%)")
    print(f"  • 包含前置条件的用例: {with_precond}/{len(blackbox_tests)} ({with_precond/len(blackbox_tests)*100:.1f}%)")
    
    return {
        "test_name": "BlackBoxTesterAgent",
        "file": input_file,
        "parsed_count": len(parsed_reqs),
        "structured_count": len(structured_reqs),
        "risk_count": len(risk_analysis),
        "blackbox_test_count": len(blackbox_tests),
        "technique_distribution": dict(technique_dist),
        "priority_distribution": priority_dist,
        "requirement_distribution": dict(req_dist),
        "test_quality_metrics": {
            "total_test_steps": total_steps,
            "average_steps_per_case": round(avg_steps, 1),
            "cases_with_test_data": with_data,
            "cases_with_preconditions": with_precond,
        },
        "blackbox_tests": blackbox_tests,
        "risk_analysis": risk_analysis,
        "errors": bb_output.get("errors", []),
    }


def main():
    print("\n" + "#"*70)
    print("# BlackBoxTesterAgent Test Suite")
    print(f"# Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#"*70)
    
    all_results = {
        "test_suite": "BlackBoxTesterAgent",
        "timestamp": datetime.now().isoformat(),
        "tests": [],
    }
    
    try:
        result = test_blackbox_tester_pipeline()
        if result:
            all_results["tests"].append(result)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        all_results["tests"].append({
            "test_name": "BlackBoxTesterAgent",
            "error": str(e)
        })
    
    # 保存结果
    output_dir = os.path.join(project_root, "outputs")
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(
        output_dir,
        f"test_blackbox_tester_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print("="*70)
    print(f"✓ Test results saved to: {output_file}")
    print("="*70 + "\n")
    
    return all_results


if __name__ == "__main__":
    main()
