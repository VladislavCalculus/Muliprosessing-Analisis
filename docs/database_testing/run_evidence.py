"""Run authorized database checks and save reproducible protocol evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def run_tests(target: str, output: str):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    command = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", target, "-v"]
    result = subprocess.run(command, cwd=ROOT, env=environment,
                            capture_output=True, text=True)
    text = result.stdout + result.stderr
    (HERE / output).write_text(text)
    print(text, end="")
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Date of the actual measurement, YYYY-MM-DD")
    parser.add_argument("--full", action="store_true", help="Also record the complete regression suite")
    args = parser.parse_args()
    test_file = "test/test_result_store.py"
    sql_files = ["src/result_store/schema.sql", "src/result_store/seed.sql"]
    source_files = sorted(path.relative_to(ROOT).as_posix()
                          for path in (ROOT / "src/result_store").rglob("*")
                          if path.suffix in {".py", ".sql"})
    if not source_files or not (ROOT / test_file).exists():
        raise SystemExit("The database implementation and test file are required")
    run_tests(test_file, "pytest.txt")
    if args.full:
        run_tests("test", "pytest-full.txt")
    evidence = {
        "date": args.date, "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version, "pytest": pytest.__version__,
        "platform": platform.system(), "test_file": test_file,
        "sql_files": sql_files,
        "sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                   for name in [*source_files, test_file]},
        "commands": [
            "PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider test/test_result_store.py -v",
        ],
    }
    (HERE / "environment.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
