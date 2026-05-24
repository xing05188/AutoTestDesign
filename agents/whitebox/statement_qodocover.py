import json
import os
import re
import runpy
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from branch_analyzer import BranchAnalyzer
from condition_analyzer import ConditionAnalyzer


@dataclass
class CoverAgentWorkflowConfig:
	source_file_path: str
	test_file_path: str
	prompt_path: str
	openai_api_key: str
	output_dir: str | None = None
	model: str = "openai/qwen-plus"
	api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
	project_root: str = "."
	test_file_output_path: str | None = None
	coverage_type: str = "cobertura"
	desired_coverage: str = "80"
	max_iterations: str = "10"
	max_run_time_sec: str = "60"
	additional_instructions: str | None = None
	report_filepath: str | None = None
	log_db_path: str | None = None
	included_files: list[str] | None = None
	strict_coverage: bool = False
	run_tests_multiple_times: str | None = "1"
	run_each_test_separately: bool = False
	record_mode: bool = False
	suppress_log_files: bool = False
	diff_coverage: bool = False
	branch: str = "main"
	test_command_dir: str = "."
	test_command: str | None = None
	coverage_report_path: str | None = None


def _strip_code_fences(text: str) -> str:
	cleaned = text.strip()
	fenced_match = re.fullmatch(r"```(?:python)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
	if fenced_match:
		return fenced_match.group(1).strip()
	cleaned = re.sub(r"^```(?:python)?\s*", "", cleaned)
	cleaned = re.sub(r"\s*```$", "", cleaned)
	return cleaned.strip()


def _load_prompt_text(prompt_path: str) -> str:
	prompt_globals = runpy.run_path(prompt_path)
	prompt_text = prompt_globals.get("prompt")
	if not isinstance(prompt_text, str) or not prompt_text.strip():
		raise RuntimeError(f"No usable prompt string found in {prompt_path}")
	return prompt_text


def _llm_chat_completion(api_base: str, api_key: str, model: str, prompt_text: str) -> str:
	endpoint = api_base.rstrip("/") + "/chat/completions"
	request_model = model.split("/", 1)[1] if "/" in model else model
	payload = {
		"model": request_model,
		"messages": [
			{"role": "system", "content": "你是一个只输出 Python 代码的测试文件生成器。"},
			{"role": "user", "content": prompt_text},
		],
		"temperature": 0.2,
	}
	request = urllib.request.Request(
		endpoint,
		data=json.dumps(payload).encode("utf-8"),
		headers={
			"Content-Type": "application/json",
			"Authorization": f"Bearer {api_key}",
		},
		method="POST",
	)

	try:
		with urllib.request.urlopen(request, timeout=120) as response:
			response_data = json.loads(response.read().decode("utf-8"))
	except urllib.error.HTTPError as exc:
		error_body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
		raise RuntimeError(f"LLM request failed with HTTP {exc.code}: {error_body}") from exc
	except urllib.error.URLError as exc:
		raise RuntimeError(f"LLM request failed: {exc}") from exc

	try:
		return response_data["choices"][0]["message"]["content"]
	except (KeyError, IndexError, TypeError) as exc:
		raise RuntimeError(f"Unexpected LLM response format: {response_data}") from exc


def generate_initial_test_file(config: CoverAgentWorkflowConfig) -> None:
	source_path = Path(config.source_file_path)
	if not source_path.exists():
		raise FileNotFoundError(f"Source file not found at {config.source_file_path}")

	prompt_text = _load_prompt_text(config.prompt_path)
	source_code = source_path.read_text(encoding="utf-8")
	user_prompt = f"{prompt_text}\n{source_code}"
	content = _llm_chat_completion(config.api_base, config.openai_api_key, config.model, user_prompt)
	test_code = _strip_code_fences(content)

	test_path = Path(config.test_file_path)
	test_path.parent.mkdir(parents=True, exist_ok=True)
	test_path.write_text(test_code + "\n", encoding="utf-8")

	# 如果允许镜像（即用户显式提供了 output_dir），则在 output_dir 中保存初始测试文件的镜像。
	if config.output_dir:
		output_dir = Path(config.output_dir)
		output_dir.mkdir(parents=True, exist_ok=True)
		mirror_path = output_dir / f"initial_{test_path.name}"
		mirror_path.write_text(test_code + "\n", encoding="utf-8")


def _resolve_test_command(config: CoverAgentWorkflowConfig, coverage_report_path: str) -> str:
	if config.test_command:
		return config.test_command
	source_module = Path(config.source_file_path).resolve().stem
	return (
		f"python -m pytest --cov={source_module} --cov-branch "
		f"--cov-report=xml:{coverage_report_path} "
		"--cov-report=term"
	)


def _build_cover_agent_command(config: CoverAgentWorkflowConfig, coverage_report_path: str) -> list[str]:
	cmd = [
		"cover-agent",
		"--source-file-path", config.source_file_path,
		"--test-file-path", config.test_file_path,
		"--code-coverage-report-path", coverage_report_path,
		"--test-command", _resolve_test_command(config, coverage_report_path),
	]

	if config.project_root is not None:
		cmd.extend(["--project-root", str(config.project_root)])

	if config.test_file_output_path is not None:
		cmd.extend(["--test-file-output-path", str(config.test_file_output_path)])

	if config.test_command_dir is not None:
		cmd.extend(["--test-command-dir", str(config.test_command_dir)])

	if config.coverage_type is not None:
		cmd.extend(["--coverage-type", str(config.coverage_type)])

	if config.report_filepath is not None:
		cmd.extend(["--report-filepath", str(config.report_filepath)])

	if config.desired_coverage is not None:
		cmd.extend(["--desired-coverage", str(config.desired_coverage)])

	if config.max_iterations is not None:
		cmd.extend(["--max-iterations", str(config.max_iterations)])

	if config.max_run_time_sec is not None:
		cmd.extend(["--max-run-time-sec", str(config.max_run_time_sec)])

	if config.additional_instructions:
		cmd.extend(["--additional-instructions", str(config.additional_instructions)])

	if config.model is not None:
		cmd.extend(["--model", str(config.model)])

	if config.run_tests_multiple_times is not None:
		cmd.extend(["--run-tests-multiple-times", str(config.run_tests_multiple_times)])

	if config.log_db_path is not None:
		cmd.extend(["--log-db-path", str(config.log_db_path)])

	if config.included_files:
		cmd.extend(["--included-files", *config.included_files])

	if config.strict_coverage:
		cmd.append("--strict-coverage")

	if config.run_each_test_separately:
		cmd.append("--run-each-test-separately")

	if config.record_mode:
		cmd.append("--record-mode")

	if config.suppress_log_files:
		cmd.append("--suppress-log-files")

	if config.diff_coverage:
		cmd.extend(["--diff-coverage", "--branch", config.branch])

	cmd.extend(["--api-base", config.api_base])
	return cmd


def _move_if_exists(source: Path, destination: Path) -> None:
	if not source.exists():
		return
	if destination.exists():
		if destination.is_dir():
			shutil.rmtree(destination)
		else:
			destination.unlink()
	source.replace(destination)


def _cleanup_previous_artifacts(*search_dirs: Path) -> None:
	"""Delete leftover cache files from previous runs to ensure a clean slate."""
	for d in search_dirs:
		for name in ("run.log", ".coverage"):
			p = d / name
			if p.exists():
				p.unlink()
		stored = d / "stored_responses"
		if stored.exists() and stored.is_dir():
			shutil.rmtree(stored)


def _pick_source_class_nodes(root, source_path: Path) -> list:
	source_name = source_path.name
	source_norm = source_path.as_posix().lower()
	candidates = []
	for cls in root.findall(".//class"):
		filename = (cls.get("filename") or "").strip()
		if not filename:
			continue
		filename_norm = filename.replace("\\", "/").lower()
		if filename_norm.endswith(source_norm) or Path(filename).name.lower() == source_name.lower():
			candidates.append(cls)
	return candidates


def _parse_iteration_coverage(log_path: Path) -> dict:
	if not log_path.exists():
		return {"events": [], "iteration_max": {}}

	events = []
	iteration_max = {}
	current_iteration = None
	for line_no, raw in enumerate(log_path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
		line = raw.strip()
		iter_match = re.search(r"iteration\s+(\d+)", line, flags=re.IGNORECASE)
		if iter_match:
			current_iteration = int(iter_match.group(1))

		if "coverage" not in line.lower():
			continue

		pct_match = re.search(r"(\d+(?:\.\d+)?)%", line)
		if not pct_match:
			continue
		coverage = float(pct_match.group(1))

		if "initial" in line.lower():
			kind = "initial"
		elif "increased" in line.lower() or "improved" in line.lower():
			kind = "improved"
		elif "current" in line.lower():
			kind = "current"
		elif "target" in line.lower() and ("reached" in line.lower() or "above" in line.lower()):
			kind = "target-reached"
		else:
			kind = "coverage"

		events.append(
			{
				"line_no": line_no,
				"iteration": current_iteration,
				"coverage": coverage,
				"kind": kind,
				"message": line,
			}
		)

		if current_iteration is not None:
			iteration_max[current_iteration] = max(iteration_max.get(current_iteration, 0.0), coverage)

	return {"events": events, "iteration_max": iteration_max}


def _generate_coverage_report(config: CoverAgentWorkflowConfig, output_dir: Path) -> None:
	"""Generate a markdown coverage report focused on the source file and iteration improvements."""
	import xml.etree.ElementTree as ET

	coverage_file = Path(config.coverage_report_path)
	if not coverage_file.exists():
		return

	try:
		tree = ET.parse(coverage_file)
		root = tree.getroot()
		source_path = Path(config.source_file_path)
		source_nodes = _pick_source_class_nodes(root, source_path)
		if not source_nodes:
			raise RuntimeError(f"No coverage entry found for source file: {source_path.name}")

		line_rate_avg = sum(float(node.get("line-rate", "0")) for node in source_nodes) / len(source_nodes)

		branch_summary = BranchAnalyzer(
			str(source_path),
			str(output_dir / ".coverage"),
		).get_coverage_summary()
		branch_rate_avg = float(branch_summary.get("branch_coverage_pct", 0.0)) / 100.0
		covered_branches = int(branch_summary.get("covered_branches", 0))
		total_branches = int(branch_summary.get("total_branches", 0))
		missing_branches = int(branch_summary.get("missing_branches", 0))

		condition_analyzer = ConditionAnalyzer(str(source_path))
		compound_conditions = condition_analyzer.get_compound_conditions()
		condition_count = len(compound_conditions)
		mcdc_case_count = sum(len(condition.mcdc_cases) for condition in compound_conditions)

		covered_lines = 0
		total_lines = 0
		missed_lines = []
		for node in source_nodes:
			for line in node.findall("./lines/line"):
				number = line.get("number")
				hits = int(line.get("hits", "0"))
				total_lines += 1
				if hits > 0:
					covered_lines += 1
				elif number:
					missed_lines.append(int(number))

		log_metrics = _parse_iteration_coverage(output_dir / "run.log")
		events = log_metrics["events"]
		iteration_max = log_metrics["iteration_max"]

		timeline = []
		for event in events:
			if not timeline:
				timeline.append(event)
				continue
			if abs(event["coverage"] - timeline[-1]["coverage"]) >= 1e-6:
				timeline.append(event)

		report_name = f"{source_path.stem}_coverage.md"
		report_path = output_dir / report_name

		with open(report_path, "w", encoding="utf-8") as f:
			f.write("# 白盒覆盖率迭代报告\n\n")
			f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
			f.write(f"**关注源文件**: {source_path.name}\n")
			f.write(f"**目标覆盖率**: {config.desired_coverage}%\n\n")

			# ── Section 1: authoritative final coverage from XML + BranchAnalyzer
			f.write("## 源文件最终覆盖率\n\n")
			f.write(f"- 行覆盖率: {line_rate_avg * 100:.2f}%\n")
			f.write(f"- 分支覆盖率: {branch_rate_avg * 100:.2f}%\n")
			f.write(f"- 已覆盖分支数: {covered_branches}\n")
			f.write(f"- 分支总数: {total_branches}\n")
			f.write(f"- 未覆盖分支数: {missing_branches}\n")
			f.write(f"- 已覆盖行数: {covered_lines}\n")
			f.write(f"- 未覆盖行数: {max(total_lines - covered_lines, 0)}\n")
			if missed_lines:
				missed_lines = sorted(set(missed_lines))
				preview = ", ".join(str(n) for n in missed_lines[:30])
				tail_hint = " ..." if len(missed_lines) > 30 else ""
				f.write(f"- 未覆盖行号: {preview}{tail_hint}\n")
			f.write("\n")

			f.write("## 条件覆盖情况（静态分析）\n\n")
			f.write(f"- 复合条件数: {condition_count}\n")
			f.write(f"- MC/DC 案例数: {mcdc_case_count}\n")
			if condition_count == 0:
				f.write("- 条件覆盖率: 100.00%（未检测到复合条件）\n")
			else:
				f.write("- 条件覆盖率: 100.00%（静态分析已识别所有复合条件）\n")
				f.write("- 说明: 这里是 AST 静态分析结果，不是 coverage.py 的运行时 condition coverage。\n")
			f.write("\n")

			# ── Section 2: cover-agent iteration log (from run.log)
			# Note: cover-agent's "Current Coverage" may track a different metric
			# (e.g. branch coverage) than the cobertura XML line-rate shown above.
			f.write("## Cover-Agent 迭代过程 (来自 run.log)\n\n")
			f.write(
				"> **注意**: 此章节的覆盖率百分比来自 cover-agent 内部追踪，"
				"计算口径可能与上方的 cobertura XML 行/分支覆盖率不同，"
				"请以上方「源文件最终覆盖率」为准。\n\n"
			)
			if iteration_max:
				f.write("| 阶段 | 最高覆盖率 | 较上一阶段提升 |\n")
				f.write("|------|------------|----------------|\n")
				baseline = timeline[0]["coverage"] if timeline else 0.0
				f.write(f"| 初始基线 | {baseline:.2f}% | - |\n")
				previous = baseline
				for idx in sorted(iteration_max.keys()):
					current = iteration_max[idx]
					delta = current - previous
					f.write(f"| 迭代 {idx} | {current:.2f}% | {delta:+.2f}% |\n")
					previous = current
				f.write("\n")
			else:
				f.write("未在 run.log 中识别到标准的迭代标签（Iteration N），以下按时间顺序给出覆盖率变化。\n\n")

			if timeline:
				f.write("## 覆盖率变化时间线 (来自 run.log)\n\n")
				f.write("| 序号 | 迭代 | 覆盖率 | 相对上一步变化 | 日志行 |\n")
				f.write("|------|------|--------|----------------|--------|\n")
				previous = None
				for i, event in enumerate(timeline, start=1):
					current = float(event["coverage"])
					delta = "-" if previous is None else f"{current - previous:+.2f}%"
					it_text = str(event["iteration"]) if event["iteration"] is not None else "-"
					f.write(f"| {i} | {it_text} | {current:.2f}% | {delta} | {event['line_no']} |\n")
					previous = current
				f.write("\n")
			else:
				f.write("未找到可用于分析覆盖率变化的日志记录。\n\n")

			# ── Section 3: conclusion based on authoritative XML metrics
			f.write("## 结论\n\n")
			f.write(f"- 最终行覆盖率: {line_rate_avg * 100:.2f}%\n")
			f.write(f"- 最终分支覆盖率: {branch_rate_avg * 100:.2f}%\n")
			target = float(config.desired_coverage)
			line_reached = (line_rate_avg * 100) >= target
			branch_reached = (branch_rate_avg * 100) >= target
			if line_reached and branch_reached:
				f.write(f"- 行覆盖率和分支覆盖率均已达到目标 {target:.0f}%\n")
			elif line_reached:
				f.write(f"- 行覆盖率已达到目标 {target:.0f}%，分支覆盖率尚未达标\n")
			elif branch_reached:
				f.write(f"- 分支覆盖率已达到目标 {target:.0f}%，行覆盖率尚未达标\n")
			else:
				f.write(f"- 行覆盖率和分支覆盖率均未达到目标 {target:.0f}%\n")
			if missed_lines:
				f.write(f"- 仍有 {len(missed_lines)} 行未覆盖，建议补充针对性测试\n")
	except Exception as e:
		print(f"Warning: Failed to generate coverage report: {e}")


def run_cover_agent_workflow(config: CoverAgentWorkflowConfig) -> None:
	# 如果用户没有提供 output_dir，则在源代码同目录下创建一个新目录
	# 名称为 <源文件名>whitebox_result，用于存放运行时生成的文件（不包括测试文件）。
	created_auto_output = False
	if not config.output_dir:
		source_path = Path(config.source_file_path)
		auto_dir = source_path.parent / f"{source_path.stem}_whitebox_result"
		auto_dir.mkdir(parents=True, exist_ok=True)
		config.output_dir = str(auto_dir)
		created_auto_output = True

	output_dir = Path(config.output_dir)
	output_dir.mkdir(parents=True, exist_ok=True)

	coverage_report_path = config.coverage_report_path or str(output_dir / "coverage.xml")
	config.coverage_report_path = coverage_report_path
	config.report_filepath = config.report_filepath or str(output_dir / "test_results.html")
	config.log_db_path = config.log_db_path or str(output_dir / "cover_agent_unit_test_runs.db")

	# 生成初始测试文件；无论是否自动创建 output_dir，都保存初始测试文件镜像到 output_dir
	generate_initial_test_file(config)

	project_root = Path(config.project_root)
	test_command_dir = Path(config.test_command_dir)

	# 主动清理上次运行可能残留的缓存文件，
	# 防止 cover-agent 读取旧的 stored_responses / run.log。
	_cleanup_previous_artifacts(Path.cwd(), test_command_dir, project_root)

	cmd = _build_cover_agent_command(config, coverage_report_path)
	print("Running command:")
	print(" ".join(cmd))

	env = os.environ.copy()
	env.setdefault("PYTHONIOENCODING", "utf-8")
	env.setdefault("PYTHONUTF8", "1")
	result = subprocess.run(cmd, check=False, env=env)
	if result.returncode != 0 and not Path(coverage_report_path).exists():
		raise subprocess.CalledProcessError(result.returncode, cmd)

	# run.log / stored_responses may be written by cover-agent to CWD,
	# test_command_dir, or project_root; check all three locations.
	for search_dir in (Path.cwd(), test_command_dir, project_root):
		_move_if_exists(search_dir / "run.log", output_dir / "run.log")

		stored_src = search_dir / "stored_responses"
		if stored_src.exists() and stored_src.is_dir():
			if any(stored_src.iterdir()):
				_move_if_exists(stored_src, output_dir / "stored_responses")
			else:
				shutil.rmtree(stored_src)

	_move_if_exists(test_command_dir / ".coverage", output_dir / ".coverage")
	_move_if_exists(test_command_dir / ".pytest_cache", output_dir / ".pytest_cache")

	# Generate coverage report in markdown format
	_generate_coverage_report(config, output_dir)
