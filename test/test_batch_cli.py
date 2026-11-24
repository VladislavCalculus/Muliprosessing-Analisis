"""Командний pipeline з SQLite перевіряється окремими subprocess-запусками."""

import json
from pathlib import Path
import subprocess
import sys
import wave

import numpy as np


def invoke(*args):
    return subprocess.run([sys.executable, "-m", "batch_proc", *map(str, args)], text=True, capture_output=True, timeout=30)


def test_cli_processes_all_files_and_reads_persistent_history(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes((16_384 * np.sin(2 * np.pi * 440 * np.arange(800) / 8_000)).astype("<i2").tobytes())
    database = tmp_path / "history.sqlite3"
    run = invoke("run", "--db", database, "--workers", "2", path, tmp_path / "absent.wav", path)
    assert run.returncode == 1, run.stderr
    events = [json.loads(line) for line in run.stdout.splitlines()]
    summary = events[-1]
    assert summary["event"] == "run_finished" and summary["status"] == "completed"
    assert summary["success_count"] == 2 and summary["failure_count"] == 1
    history = invoke("history", "--db", database, "--run-id", summary["run_id"])
    assert history.returncode == 0, history.stderr
    files = json.loads(history.stdout)["files"]
    assert {item["source_id"] for item in files} == {"file-1", "file-2", "file-3"}
    assert sum(bool(item["peaks"]) for item in files) == 2


def test_invalid_filter_and_missing_history_do_not_create_database(tmp_path: Path) -> None:
    database = tmp_path / "not-created.sqlite3"
    invalid = invoke("run", "--db", database, "--filter", "lowpass", tmp_path / "any.wav")
    assert invalid.returncode == 2 and not database.exists()
    missing = invoke("history", "--db", database)
    assert missing.returncode == 2 and not database.exists()
