"""
Test InputParserAgent with real test files
使用真实的 requirements_test.csv 和 requirements_test.txt 进行测试
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
from graph.state import create_initial_state


def test_real_csv():
    """使用真实 CSV 文件进行测试"""
    print("\n" + "="*60)
    print("TEST: Real CSV File (requirements_test.csv)")
    print("="*60)
    
    csv_file = os.path.join(project_root, "tests", "requirements_test.csv")
    
    with open(csv_file, "r", encoding="utf-8") as f:
        csv_content = f.read()
    
    print(f"Input file: {csv_file}")
    print(f"File size: {len(csv_content)} bytes")
    print(f"Preview:\n{csv_content[:200]}...\n")
    
    state = create_initial_state(raw_input=csv_content, input_format="auto")
    output = input_parser_node(state)
    
    print(f"✓ Input format detected: {output.get('input_format')}")
    parsed = output.get("parsed_requirements", [])
    print(f"✓ Parsed count: {len(parsed)}")
    print(f"✓ Progress: {output.get('progress_messages')}")
    
    if output.get("errors"):
        print(f"✗ Errors: {output.get('errors')}")
    else:
        print("✓ No errors")
    
    # 显示所有解析结果
    if parsed:
        print(f"\nAll parsed requirements:")
        for i, req in enumerate(parsed, 1):
            print(f"\n[{i}] ID: {req.get('req_id')}")
            print(f"    Title: {req.get('title')}")
            print(f"    Description: {req.get('description')}")
    
    return {
        "test_name": "Real CSV File",
        "file": csv_file,
        "input_size": len(csv_content),
        "parsed_count": len(parsed),
        "parsed_requirements": parsed,
        "errors": output.get("errors", []),
    }


def test_real_text():
    """使用真实文本文件进行测试"""
    print("\n" + "="*60)
    print("TEST: Real Text File (requirements_test.txt)")
    print("="*60)
    
    txt_file = os.path.join(project_root, "tests", "requirements_test.txt")
    
    with open(txt_file, "r", encoding="utf-8") as f:
        txt_content = f.read()
    
    print(f"Input file: {txt_file}")
    print(f"File size: {len(txt_content)} bytes")
    print(f"Preview:\n{txt_content[:200]}...\n")
    
    state = create_initial_state(raw_input=txt_content, input_format="auto")
    output = input_parser_node(state)
    
    print(f"✓ Input format detected: {output.get('input_format')}")
    parsed = output.get("parsed_requirements", [])
    print(f"✓ Parsed count: {len(parsed)}")
    print(f"✓ Progress: {output.get('progress_messages')}")
    
    if output.get("errors"):
        print(f"✗ Errors: {output.get('errors')}")
    else:
        print("✓ No errors")
    
    # 显示所有解析结果
    if parsed:
        print(f"\nAll parsed requirements:")
        for i, req in enumerate(parsed, 1):
            print(f"\n[{i}] ID: {req.get('req_id')}")
            print(f"    Title: {req.get('title')}")
            print(f"    Description: {req.get('description')}")
    
    return {
        "test_name": "Real Text File",
        "file": txt_file,
        "input_size": len(txt_content),
        "parsed_count": len(parsed),
        "parsed_requirements": parsed,
        "errors": output.get("errors", []),
    }


def main():
    print("\n" + "#"*60)
    print("# InputParserAgent - Real Test Files")
    print(f"# Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#"*60)
    
    all_results = {
        "test_suite": "InputParserAgent - Real Test Files",
        "timestamp": datetime.now().isoformat(),
        "tests": [],
    }
    
    # # CSV 测试
    # try:
    #     result_csv = test_real_csv()
    #     all_results["tests"].append(result_csv)
    # except Exception as e:
    #     print(f"✗ CSV test failed: {e}")
    #     import traceback
    #     traceback.print_exc()
    #     all_results["tests"].append({"test_name": "Real CSV File", "error": str(e)})
    
    # 文本测试
    try:
        result_txt = test_real_text()
        all_results["tests"].append(result_txt)
    except Exception as e:
        print(f"✗ Text test failed: {e}")
        import traceback
        traceback.print_exc()
        all_results["tests"].append({"test_name": "Real Text File", "error": str(e)})
    
    # 保存结果
    output_dir = os.path.join(project_root, "outputs")
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(
        output_dir,
        f"test_input_parser_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*60)
    print(f"✓ Test results saved to: {output_file}")
    print("="*60 + "\n")
    
    # 统计
    csv_parsed = all_results["tests"][0].get("parsed_count", 0) if len(all_results["tests"]) > 0 else 0
    txt_parsed = all_results["tests"][1].get("parsed_count", 0) if len(all_results["tests"]) > 1 else 0
    
    print(f"Summary:")
    print(f"  CSV requirements parsed: {csv_parsed}")
    print(f"  TXT requirements parsed: {txt_parsed}")
    print(f"  Total requirements: {csv_parsed + txt_parsed}\n")
    
    return all_results


if __name__ == "__main__":
    main()
