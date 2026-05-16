import os
from pathlib import Path

from dotenv import load_dotenv

from interface import CoverAgentWorkflowConfig, run_cover_agent_workflow


def main() -> None:
    load_dotenv()

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise RuntimeError("未找到 OPENAI_API_KEY，请先在 .env 中配置。")

    output_dir = Path("examples") / "ex1" / "test_result"
    config = CoverAgentWorkflowConfig(
        source_file_path="examples\\ex1\\calculator.py",
        test_file_path="examples\\ex1\\test_calculater.py",
        output_dir=str(output_dir),
        prompt_path="prompt.py",
        openai_api_key=openai_api_key,
        model="openai/qwen-plus",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        project_root=".",
        test_file_output_path=None,
        coverage_type="cobertura",
        desired_coverage="80",
        max_iterations="10",
        max_run_time_sec="60",
        additional_instructions=None,
        report_filepath=str(output_dir / "test_results.html"),
        log_db_path=str(output_dir / "cover_agent_unit_test_runs.db"),
        included_files=None,
        strict_coverage=False,
        run_tests_multiple_times="1",
        run_each_test_separately=False,
        record_mode=False,
        suppress_log_files=False,
        diff_coverage=False,
        branch="main",
        test_command_dir=".",
        test_command=None,
        coverage_report_path=str(output_dir / "coverage.xml"),
    )

    run_cover_agent_workflow(config)


if __name__ == "__main__":
    main()