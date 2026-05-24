"""
ex3 — 语句 + 分支 + 条件覆盖测试 (full mode)
依次运行 qodo-cover（语句覆盖）和 CoverageImprovementPipeline（分支/条件覆盖）。
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "agents" / "whitebox"))

from whitebox_test import WhiteboxTestRunner


def main() -> None:
    load_dotenv()
    here = Path(__file__).parent

    runner = WhiteboxTestRunner(
        source_file=str(here / "source_file" / "calculator.py"),
        test_file=str(here / "test_calculator.py"),
        mode="full",
    )
    runner.run()


if __name__ == "__main__":
    main()
