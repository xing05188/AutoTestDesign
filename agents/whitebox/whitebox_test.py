"""
WhiteboxTestRunner - 白盒测试集成运行器

支持两种模式:
- statement: 仅语句覆盖 (qodo-cover)，生成基础测试和覆盖率报告
- full: 语句 + 分支 + 条件覆盖，在 qodo-cover 基础上迭代提升分支覆盖率

使用示例:
    from whitebox_test import WhiteboxTestRunner

    runner = WhiteboxTestRunner(
        source_file="calculator.py",
        test_file="test_calculater.py",
        mode="full",
    )
    runner.run()
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Path setup (must happen before importing whitebox submodules)
# ─────────────────────────────────────────────────────────────────────────────

_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[1]  # agents/whitebox -> agents -> project root
_WHITEBOX_ROOT = _THIS_FILE.parent      # agents/whitebox

sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_WHITEBOX_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# WhiteboxTestRunner
# ─────────────────────────────────────────────────────────────────────────────

class WhiteboxTestRunner:
    """
    白盒测试集成运行器。

    Parameters
    ----------
    source_file : str
        待测 Python 源文件路径。
    test_file : str
        测试文件路径（qodo-cover 会覆写此文件作为初始测试文件）。
    mode : str
        "statement" — 仅语句覆盖 (qodo-cover)
        "full" — 语句 + 分支 + 条件覆盖 (qodo-cover + CoverageImprovementPipeline)
    api_key : str | None
        OpenAI 兼容 API key，默认从 OPENAI_API_KEY 环境变量读取。
    api_base : str | None
        API 基地址，默认从 OPENAI_API_URL 环境变量读取。
    model : str | None
        模型标识，默认从 OPENAI_MODEL 环境变量读取。
    prompt_path : str | None
        qodo-cover 提示词文件路径，默认使用 agents/whitebox/prompt.py。
    project_root : str | None
        项目根目录，默认自动检测。
    statement_target : str
        语句覆盖率目标 (qodo-cover)，默认 "80"。
    statement_max_iterations : str
        qodo-cover 最大迭代次数，默认 "10"。
    statement_max_run_time : str
        qodo-cover 最长运行时间（秒），默认 "60"。
    branch_target : float
        分支覆盖率目标 (Pipeline)，默认 90.0。
    branch_max_iterations : int
        分支覆盖最大迭代次数，默认 3。
    include_conditions : bool
        是否启用 MC/DC 条件覆盖，默认 True。
    """

    def __init__(
        self,
        source_file: str,
        test_file: str,
        mode: str = "full",
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        prompt_path: str | None = None,
        project_root: str | None = None,
        statement_target: str = "80",
        statement_max_iterations: str = "10",
        statement_max_run_time: str = "60",
        branch_target: float = 90.0,
        branch_max_iterations: int = 3,
        include_conditions: bool = True,
    ) -> None:
        if mode not in ("statement", "full"):
            raise ValueError(f"mode must be 'statement' or 'full', got: {mode}")

        self.mode = mode
        self.source_path = Path(source_file).resolve()
        self.test_path = Path(test_file).resolve()
        self.statement_target = statement_target
        self.statement_max_iterations = statement_max_iterations
        self.statement_max_run_time = statement_max_run_time
        self.branch_target = branch_target
        self.branch_max_iterations = branch_max_iterations
        self.include_conditions = include_conditions

        # API 凭据
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.api_base = api_base or os.environ.get("OPENAI_API_URL", "")
        self.model = model or os.environ.get("OPENAI_MODEL", "")
        if not self.api_key:
            raise RuntimeError("未找到 API key，请通过参数传入或设置 OPENAI_API_KEY 环境变量")
        if not self.api_base:
            raise RuntimeError("未找到 API base URL，请通过参数传入或设置 OPENAI_API_URL 环境变量")
        if not self.model:
            raise RuntimeError("未找到 model，请通过参数传入或设置 OPENAI_MODEL 环境变量")

        # 路径
        self.project_root = Path(project_root) if project_root else _PROJECT_ROOT
        self.prompt_path = prompt_path or str(_WHITEBOX_ROOT / "prompt.py")

        # 结果输出目录：源代码同级目录下的 <source_name>_whitebox_result/
        self.result_dir = self.source_path.parent / f"{self.source_path.stem}_whitebox_result"
        self.report_path = self.result_dir / f"{self.source_path.stem}_coverage.md"

    # ── public API ──────────────────────────────────────────────────────────

    def run(self) -> dict[str, Any]:
        """
        执行白盒测试流程。

        Returns
        -------
        dict
            包含 mode, result_dir, report_path, pipeline_result (仅 full 模式)。
        """
        self.result_dir.mkdir(parents=True, exist_ok=True)

        self._print_header()

        if self.mode == "statement":
            self._run_statement_only()
            return {
                "mode": "statement",
                "result_dir": str(self.result_dir),
                "report_path": str(self.report_path),
            }

        # full mode
        pipeline_result = self._run_full()
        return {
            "mode": "full",
            "result_dir": str(self.result_dir),
            "report_path": str(self.report_path),
            "pipeline_result": pipeline_result,
        }

    # ── mode implementations ────────────────────────────────────────────────

    def _run_statement_only(self) -> None:
        """仅运行语句覆盖 (qodo-cover)。"""
        config = self._build_qodocover_config()
        from agents.whitebox.statement_qodocover import run_cover_agent_workflow
        run_cover_agent_workflow(config)
        print(f"\n[WhiteboxTest] 语句覆盖报告已生成: {self.report_path}")

    def _run_full(self) -> Any:
        """
        运行语句 + 分支 + 条件覆盖：
        1. qodo-cover 生成初始测试和语句覆盖报告
        2. CoverageImprovementPipeline 迭代提升分支/条件覆盖率
        3. 在已有报告末尾追加分支/条件覆盖迭代结果
        """
        # Phase 1: 语句覆盖
        self._print_phase("Phase 1/2: 语句覆盖 (qodo-cover)")
        config = self._build_qodocover_config()
        from agents.whitebox.statement_qodocover import run_cover_agent_workflow
        run_cover_agent_workflow(config)

        # Phase 2: 分支/条件覆盖
        self._print_phase("Phase 2/2: 分支/条件覆盖 (CoverageImprovementPipeline)")
        from agents.whitebox.pipeline import CoverageImprovementPipeline

        # 切换到 test 文件所在目录运行 pipeline，
        # 确保 pytest-cov 的 .coverage 文件写入正确位置
        test_dir = self.test_path.parent
        saved_cwd = os.getcwd()
        os.chdir(test_dir)
        try:
            pipeline = CoverageImprovementPipeline(
                source_file=str(self.source_path),
                test_file=str(self.test_path),
                api_key=self.api_key,
                api_base=self.api_base,
                model=self.model,
                include_conditions=self.include_conditions,
                coverage_data_file=".coverage",
            )
            result = pipeline.run(
                target_branch_coverage=self.branch_target,
                max_iterations=self.branch_max_iterations,
                test_paths=[str(self.test_path)],
            )
        finally:
            # 将 pipeline 产生的 .coverage 文件移入结果目录
            for fname in (".coverage", ".pytest_cache"):
                candidate = test_dir / fname
                if candidate.exists():
                    dest = self.result_dir / fname
                    if dest.exists():
                        if dest.is_dir():
                            import shutil
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    candidate.rename(dest)
            os.chdir(saved_cwd)

        # 在已有报告基础上追加分支/条件覆盖迭代结果
        self._extend_report_with_pipeline(result)

        print(f"\n[WhiteboxTest] 完整覆盖率报告已生成: {self.report_path}")
        return result

    # ── helpers ─────────────────────────────────────────────────────────────

    def _build_qodocover_config(self):
        """根据当前设置构建 CoverAgentWorkflowConfig。"""
        from agents.whitebox.statement_qodocover import CoverAgentWorkflowConfig

        return CoverAgentWorkflowConfig(
            source_file_path=str(self.source_path),
            test_file_path=str(self.test_path),
            output_dir=str(self.result_dir),
            prompt_path=self.prompt_path,
            openai_api_key=self.api_key,
            model=self.model,
            api_base=self.api_base,
            project_root=str(self.project_root),
            test_file_output_path=None,
            coverage_type="cobertura",
            desired_coverage=self.statement_target,
            max_iterations=self.statement_max_iterations,
            max_run_time_sec=self.statement_max_run_time,
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
            test_command_dir=str(self.test_path.parent),
            test_command=None,
            coverage_report_path=None,
        )

    def _extend_report_with_pipeline(self, pipeline_result: Any) -> None:
        """在已有 qodo-cover 报告末尾追加分支/条件覆盖迭代结果。"""
        if not self.report_path.exists():
            print("[WhiteboxTest] 警告: 未找到 qodo-cover 报告，将创建新报告。")
            self._write_pipeline_only_report(pipeline_result)
            return

        # qodo-cover 报告由 _generate_coverage_report 生成，结尾是 "## 结论"
        # 我们在末尾追加新的章节。
        with open(self.report_path, "a", encoding="utf-8") as f:
            f.write(self._format_pipeline_section(pipeline_result))

    def _write_pipeline_only_report(self, pipeline_result: Any) -> None:
        """当 qodo-cover 报告不存在时，单独写入 pipeline 结果报告。"""
        with open(self.report_path, "w", encoding="utf-8") as f:
            f.write("# 白盒覆盖率迭代报告\n\n")
            f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**关注源文件**: {self.source_path.name}\n\n")
            f.write(self._format_pipeline_section(pipeline_result))

    def _format_pipeline_section(self, result: Any) -> str:
        """将 PipelineResult 格式化为 Markdown 报告章节。"""
        iterations = getattr(result, "iterations", [])
        final_cov = getattr(result, "final_branch_coverage", 0.0)
        target_reached = getattr(result, "target_reached", False)
        total_added = getattr(result, "total_tests_added", 0)

        lines = [
            "## 分支/条件覆盖迭代改进 (CoverageImprovementPipeline)",
            "",
            f"- **目标分支覆盖率**: {getattr(result, 'target_coverage', self.branch_target):.1f}%",
            f"- **最终分支覆盖率**: {final_cov:.1f}%",
            f"- **目标达成**: {'是' if target_reached else '否'}",
            f"- **迭代次数**: {len(iterations)}",
            f"- **新增测试数**: {total_added}",
            "",
        ]

        if iterations:
            lines.append("### 迭代详情")
            lines.append("")
            lines.append("| 迭代 | 覆盖前 | 覆盖后 | 提升 | 缺失分支(前) | 缺失分支(后) | 生成测试 | 语法 |")
            lines.append("|------|--------|--------|------|-------------|-------------|---------|------|")
            for it in iterations:
                delta = it.branch_coverage_after - it.branch_coverage_before
                syntax = "OK" if it.syntax_ok else "ERROR"
                lines.append(
                    f"| {it.iteration} "
                    f"| {it.branch_coverage_before:.1f}% "
                    f"| {it.branch_coverage_after:.1f}% "
                    f"| {delta:+.1f}% "
                    f"| {it.missing_branches_before} "
                    f"| {it.missing_branches_after} "
                    f"| {it.generated_tests} "
                    f"| {syntax} |"
                )
            lines.append("")

            # 计算累计提升
            first_before = iterations[0].branch_coverage_before
            total_gain = final_cov - first_before
            lines.append("### 结论")
            lines.append("")
            lines.append(
                f"- 从初始分支覆盖率 {first_before:.1f}% 提升到 {final_cov:.1f}%，"
                f"累计提升 {total_gain:+.1f}%"
            )
            lines.append(
                f"- 共经历 {len(iterations)} 轮迭代，新增 {total_added} 个测试用例"
            )
            if target_reached:
                lines.append(f"- 已达到目标覆盖率 {getattr(result, 'target_coverage', self.branch_target):.1f}%")
            else:
                lines.append(
                    f"- 未达到目标覆盖率 {getattr(result, 'target_coverage', self.branch_target):.1f}%，"
                    f"差值 {getattr(result, 'target_coverage', self.branch_target) - final_cov:.1f}%"
                )
            lines.append("")

        return "\n".join(lines)

    # ── display ─────────────────────────────────────────────────────────────

    def _print_header(self) -> None:
        """打印运行配置摘要。"""
        mode_label = "语句覆盖" if self.mode == "statement" else "语句 + 分支 + 条件覆盖"
        print("═" * 60)
        print("WhiteboxTestRunner — 白盒测试集成运行器")
        print("═" * 60)
        print(f"  模式        : {mode_label}")
        print(f"  源文件      : {self.source_path}")
        print(f"  测试文件    : {self.test_path}")
        print(f"  结果目录    : {self.result_dir}")
        print(f"  报告路径    : {self.report_path}")
        if self.mode == "full":
            print(f"  语句目标    : {self.statement_target}%")
            print(f"  分支目标    : {self.branch_target:.1f}%")
            print(f"  分支迭代    : {self.branch_max_iterations}")
            print(f"  条件覆盖    : {'是' if self.include_conditions else '否'}")
        print("═" * 60)

    @staticmethod
    def _print_phase(title: str) -> None:
        print(f"\n{'─' * 60}")
        print(f"  {title}")
        print(f"{'─' * 60}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """从命令行运行白盒测试（通过环境变量 .env 获取配置）。"""
    from dotenv import load_dotenv
    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser(
        description="WhiteboxTestRunner — 白盒测试集成运行器",
    )
    parser.add_argument(
        "--source", "-s", required=True,
        help="待测 Python 源文件路径",
    )
    parser.add_argument(
        "--test", "-t", required=True,
        help="测试文件路径（将被 qodo-cover 覆写）",
    )
    parser.add_argument(
        "--mode", "-m", choices=["statement", "full"], default="full",
        help="测试模式: statement (仅语句覆盖) | full (语句+分支+条件覆盖, 默认)",
    )
    parser.add_argument(
        "--statement-target", default="80",
        help="语句覆盖率目标 (默认 80)",
    )
    parser.add_argument(
        "--branch-target", type=float, default=90.0,
        help="分支覆盖率目标 (默认 90.0)",
    )
    parser.add_argument(
        "--branch-max-iterations", type=int, default=3,
        help="分支覆盖最大迭代次数 (默认 3)",
    )
    parser.add_argument(
        "--no-conditions", action="store_true",
        help="禁用 MC/DC 条件覆盖",
    )
    args = parser.parse_args()

    runner = WhiteboxTestRunner(
        source_file=args.source,
        test_file=args.test,
        mode=args.mode,
        statement_target=args.statement_target,
        branch_target=args.branch_target,
        branch_max_iterations=args.branch_max_iterations,
        include_conditions=not args.no_conditions,
    )
    runner.run()


if __name__ == "__main__":
    main()
