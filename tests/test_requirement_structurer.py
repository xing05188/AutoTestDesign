"""
Test RequirementStructurerAgent
集成测试：InputParserAgent → RequirementStructurerAgent
验证需求深度结构化分析是否正确提取可测试元素
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
from graph.state import create_initial_state


def test_requirement_structurer():
    """
    集成测试：
    1. 从真实 CSV 文件读取需求
    2. 通过 InputParserAgent 解析
    3. 通过 RequirementStructurerAgent 结构化
    4. 验证提取的结构化元素
    """
    print("\n" + "="*60)
    print("TEST: RequirementStructurerAgent - Full Pipeline")
    print("="*60)

    input_file = os.path.join(project_root, "tests", "requirements_test.txt")

    with open(input_file, "r", encoding="utf-8") as f:
        csv_content = f.read()

    print(f"📄 Input file: {input_file}")
    print(f"📊 File size: {len(csv_content)} bytes\n")
    
    # Step 1: InputParser
    print("Step 1: InputParserAgent 解析需求...")
    state = create_initial_state(raw_input=csv_content, input_format="auto")
    parse_output = input_parser_node(state)
    
    parsed_reqs = parse_output.get("parsed_requirements", [])
    print(f"✓ 解析完成：{len(parsed_reqs)} 条需求")
    
    if not parsed_reqs:
        print("✗ 没有解析到需求，无法继续")
        return None
    
    # 显示解析结果样本
    print(f"\n解析样本（第一条需求）：")
    req_sample = parsed_reqs[0]
    print(f"  req_id: {req_sample.get('req_id')}")
    print(f"  title: {req_sample.get('title')}")
    print(f"  description: {req_sample.get('description')}\n")
    
    # Step 2: RequirementStructurer
    print("Step 2: RequirementStructurerAgent 深度结构化分析...")
    state.update(parse_output)
    struct_output = requirement_structurer_node(state)
    
    structured_reqs = struct_output.get("structured_requirements", [])
    print(f"✓ 结构化完成：{len(structured_reqs)} 条需求")
    
    # 显示结构化结果详情
    print(f"\n结构化样本（第一条需求）：")
    if structured_reqs:
        struct_sample = structured_reqs[0]
        print(f"  req_id: {struct_sample.get('req_id')}")
        print(f"  title: {struct_sample.get('title')}")
        print(f"  domain: {struct_sample.get('domain')}")
        
        input_fields = struct_sample.get("input_fields", [])
        print(f"  📝 输入字段数: {len(input_fields)}")
        if input_fields:
            for field in input_fields[:2]:  # 显示前2个
                print(f"    - {field.get('name')} ({field.get('data_type')}): {field.get('description')}")
        
        data_ranges = struct_sample.get("data_ranges", [])
        print(f"  📏 数据范围数: {len(data_ranges)}")
        if data_ranges:
            for drange in data_ranges[:2]:  # 显示前2个
                print(f"    - {drange.get('field_name')}: [{drange.get('min_value')} ~ {drange.get('max_value')}]")
        
        conditions = struct_sample.get("conditions", [])
        print(f"  🔀 业务条件数: {len(conditions)}")
        if conditions:
            for cond in conditions[:2]:  # 显示前2个
                print(f"    - {cond}")
        
        actions = struct_sample.get("expected_actions", [])
        print(f"  ✅ 预期行为数: {len(actions)}")
        if actions:
            for act in actions[:2]:  # 显示前2个
                print(f"    - {act}")
    
    # 统计信息
    total_fields = sum(len(r.get("input_fields", [])) for r in structured_reqs)
    total_ranges = sum(len(r.get("data_ranges", [])) for r in structured_reqs)
    total_conditions = sum(len(r.get("conditions", [])) for r in structured_reqs)
    total_actions = sum(len(r.get("expected_actions", [])) for r in structured_reqs)
    
    print(f"\n📊 全局统计：")
    print(f"  总需求数: {len(structured_reqs)}")
    print(f"  总输入字段数: {total_fields}")
    print(f"  总数据范围数: {total_ranges}")
    print(f"  总业务条件数: {total_conditions}")
    print(f"  总预期行为数: {total_actions}")
    
    # 显示所有需求的摘要
    print(f"\n📋 所有需求摘要：")
    for i, req in enumerate(structured_reqs, 1):
        fields_count = len(req.get("input_fields", []))
        ranges_count = len(req.get("data_ranges", []))
        print(f"  [{i}] {req.get('req_id'):10} | {req.get('title'):20} | "
              f"字段:{fields_count:2} 范围:{ranges_count:2} | {req.get('domain', 'general')}")
    
    return {
        "test_name": "RequirementStructurerAgent",
        "file": input_file,
        "parsed_count": len(parsed_reqs),
        "structured_count": len(structured_reqs),
        "total_fields": total_fields,
        "total_ranges": total_ranges,
        "total_conditions": total_conditions,
        "total_actions": total_actions,
        "structured_requirements": structured_reqs,
        "parse_progress": parse_output.get("progress_messages", []),
        "struct_progress": struct_output.get("progress_messages", []),
        "errors": struct_output.get("errors", []),
    }


def main():
    print("\n" + "#"*60)
    print("# RequirementStructurerAgent Test Suite")
    print(f"# Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#"*60)
    
    all_results = {
        "test_suite": "RequirementStructurerAgent",
        "timestamp": datetime.now().isoformat(),
        "tests": [],
    }
    
    try:
        result = test_requirement_structurer()
        if result:
            all_results["tests"].append(result)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        all_results["tests"].append({
            "test_name": "RequirementStructurerAgent",
            "error": str(e)
        })
    
    # 保存结果
    output_dir = os.path.join(project_root, "outputs")
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(
        output_dir,
        f"test_requirement_structurer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*60)
    print(f"✓ Test results saved to: {output_file}")
    print("="*60 + "\n")
    
    return all_results


if __name__ == "__main__":
    main()
