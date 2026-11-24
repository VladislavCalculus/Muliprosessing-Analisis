"""Create a reproducible good/bad/good WAV batch and retain its SQLite history."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

import numpy as np
from scipy.io import wavfile

from batch_proc.__main__ import main as batch_main
from result_store import ResultStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="new directory; existing contents are never overwritten")
    args = parser.parse_args()
    if args.output_dir is None:
        directory = Path(tempfile.mkdtemp(prefix="mlt-batch-demo-"))
    else:
        directory = args.output_dir.resolve()
        directory.mkdir(parents=True, exist_ok=False)
    rate = 8_000
    time_s = np.arange(rate) / rate
    mono = np.rint(16_384 * np.sin(2 * np.pi * 440 * time_s)).astype(np.int16)
    wavfile.write(directory / "first.wav", rate, mono)
    (directory / "broken.wav").write_text("not a WAV file")
    wavfile.write(directory / "stereo.wav", rate, np.column_stack((mono, mono)))
    database = directory / "history.sqlite3"
    code = batch_main([
        "run", "--db", str(database), "--workers", "2",
        str(directory / "first.wav"), str(directory / "broken.wav"), str(directory / "stereo.wav"),
    ])
    with ResultStore(database) as store:
        run = store.list_runs()[0]
    print(f"Demo retained in {directory}")
    print(f"Read history: python -m batch_proc history --db {database} --run-id {run['run_id']}")
    return 0 if code == 1 and run["success_count"] == 2 and run["failure_count"] == 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
