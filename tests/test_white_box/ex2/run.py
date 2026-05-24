"""
ex2 — 语句覆盖测试 (statement mode)
仅运行 qodo-cover 进行语句覆盖。
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
        mode="statement",
    )
    runner.run()


if __name__ == "__main__":
    main()
