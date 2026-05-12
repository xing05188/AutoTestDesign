"""
Test RiskAnalyzerAgent
集成测试：InputParser → RequirementStructurer → RiskAnalyzer
验证风险评分和优先级分配是否正确
"""

import json
import os
import sys
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from agents.input_parser import input_parser_node
from agents.requirement_structurer import requirement_structurer_node
from agents.risk_analyzer import risk_analyzer_node
from graph.state import create_initial_state


def test_risk_analyzer_pipeline():
    """
    完整流程测试：
    1. InputParserAgent → 解析需求
    2. RequirementStructurerAgent → 结构化分析
    3. RiskAnalyzerAgent → 风险评估
    """
    print("\n" + "="*60)
    print("TEST: RiskAnalyzerAgent - Complete Pipeline")
    print("="*60)
    
    csv_file = os.path.join(project_root, "tests", "requirements_test.csv")
    
    with open(csv_file, "r", encoding="utf-8") as f:
        csv_content = f.read()
    
    print(f"📄 Input file: {csv_file}")
    print(f"📊 File size: {len(csv_content)} bytes\n")
    
    # Step 1: InputParser
    print("Step 1: InputParserAgent 解析需求...")
    state = create_initial_state(raw_input=csv_content, input_format="auto")
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
    
    if risk_output.get("errors"):
        print(f"⚠ 警告: {risk_output.get('errors')}")
    
    # 统计风险优先级分布
    priority_dist = {"High": 0, "Medium": 0, "Low": 0}
    for risk in risk_analysis:
        priority = risk.get("priority", "Medium")
        if priority in priority_dist:
            priority_dist[priority] += 1
    
    print("📊 风险优先级分布：")
    print(f"  🔴 High: {priority_dist['High']} 个")
    print(f"  🟡 Medium: {priority_dist['Medium']} 个")
    print(f"  🟢 Low: {priority_dist['Low']} 个\n")
    
    # 显示所有风险评分详情
    print("📋 详细风险评分（按优先级排序）：\n")
    
    # 按优先级排序
    sorted_risks = sorted(risk_analysis, key=lambda x: {
        "High": 0,
        "Medium": 1,
        "Low": 2
    }.get(x.get("priority", "Medium"), 3))
    
    for i, risk in enumerate(sorted_risks, 1):
        priority = risk.get("priority", "Medium")
        priority_icon = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(priority, "⚪")
        
        print(f"[{i}] {priority_icon} {risk.get('req_id'):10} | {risk.get('title'):20}")
        print(f"    Impact:{risk.get('impact'):2}  Probability:{risk.get('probability'):2}  "
              f"Complexity:{risk.get('complexity'):2}  "
              f"Change:{risk.get('change_frequency', 'N/A'):2}")
        print(f"    Risk Score: {risk.get('risk_score')}")
        
        risk_factors = risk.get("risk_factors", [])
        if risk_factors:
            print(f"    Risk Factors: {'; '.join(risk_factors[:2])}")
        
        mitigation = risk.get("mitigation", "")
        if mitigation:
            print(f"    Mitigation: {mitigation}")
        
        print()
    
    # 计算平均风险分
    avg_risk = sum(r.get("risk_score", 0) for r in risk_analysis) / len(risk_analysis) if risk_analysis else 0
    print(f"📈 平均风险分：{avg_risk:.1f}\n")
    
    return {
        "test_name": "RiskAnalyzerAgent",
        "file": csv_file,
        "parsed_count": len(parsed_reqs),
        "structured_count": len(structured_reqs),
        "risk_count": len(risk_analysis),
        "priority_distribution": priority_dist,
        "average_risk_score": round(avg_risk, 1),
        "risk_analysis": risk_analysis,
        "progress": {
            "parse": parse_output.get("progress_messages", []),
            "struct": struct_output.get("progress_messages", []),
            "risk": risk_output.get("progress_messages", []),
        },
        "errors": risk_output.get("errors", []),
    }


def main():
    print("\n" + "#"*60)
    print("# RiskAnalyzerAgent Test Suite")
    print(f"# Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#"*60)
    
    all_results = {
        "test_suite": "RiskAnalyzerAgent",
        "timestamp": datetime.now().isoformat(),
        "tests": [],
    }
    
    try:
        result = test_risk_analyzer_pipeline()
        if result:
            all_results["tests"].append(result)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        all_results["tests"].append({
            "test_name": "RiskAnalyzerAgent",
            "error": str(e)
        })
    
    # 保存结果
    output_dir = os.path.join(project_root, "outputs")
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(
        output_dir,
        f"test_risk_analyzer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print("="*60)
    print(f"✓ Test results saved to: {output_file}")
    print("="*60 + "\n")
    
    return all_results


if __name__ == "__main__":
    main()
