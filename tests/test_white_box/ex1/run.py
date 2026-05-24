import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path so top-level packages (like `agents`) can be imported
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

# `agents/whitebox` contains modules that currently use direct sibling imports.
WHITEBOX_ROOT = PROJECT_ROOT / "agents" / "whitebox"
sys.path.insert(0, str(WHITEBOX_ROOT))

from agents.whitebox.statement_qodocover import CoverAgentWorkflowConfig, run_cover_agent_workflow
from agents.whitebox.pipeline import CoverageImprovementPipeline


def main() -> None:
    load_dotenv()

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise RuntimeError("未找到 OPENAI_API_KEY，请先在 .env 中配置。")

    api_base = os.getenv("OPENAI_API_URL")
    if not api_base:
        raise RuntimeError("未找到 OPENAI_API_URL，请先在 .env 中配置。")

    model = os.getenv("OPENAI_MODEL")
    if not model:
        raise RuntimeError("未找到 OPENAI_MODEL，请先在 .env 中配置。")

    here = Path(__file__).parent
    prompt_path = Path(__file__).resolve().parents[3] / "agents" / "whitebox" / "prompt.py"

    config = CoverAgentWorkflowConfig(
        source_file_path=str(here / "calculator.py"),
        test_file_path=str(here / "test_calculater.py"),
        output_dir=None,
        prompt_path=str(prompt_path),
        openai_api_key=openai_api_key,
        model=model,
        api_base=api_base,
        project_root=str(Path(__file__).resolve().parents[3]),
        test_file_output_path=None,
        coverage_type="cobertura",
        desired_coverage="80",
        max_iterations="10",
        max_run_time_sec="60",
        additional_instructions=None,
        report_filepath=None,
        log_db_path=None,
        included_files=None,
        strict_coverage=False,
        run_tests_multiple_times="1",
        run_each_test_separately=False,
        record_mode=False,
        suppress_log_files=False,
        diff_coverage=False,
        branch="main",
        test_command_dir=str(here),
        test_command=None,
        coverage_report_path=None,
    )

    run_cover_agent_workflow(config)

    pipeline = CoverageImprovementPipeline(
        source_file=str(here / "calculator.py"),
        test_file=str(here / "test_calculater.py"),
        api_key=openai_api_key,
        api_base=api_base,
        model=model,
        include_conditions=True,
    )
    result = pipeline.run(
        target_branch_coverage=90.0,
        max_iterations=3,
        test_paths=[str(here / "test_calculater.py")],
    )


if __name__ == "__main__":
    main()
