"""Run parallel WAV analysis and read its SQLite history without a UI."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

from audio_contracts import FileJob
from result_store import ResultStore
from signal_proc import FilterConfig, PeakConfig

from .schedule import iter_batch


def _print(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="process WAV files and save all outcomes")
    run.add_argument("paths", nargs="+", type=Path)
    run.add_argument("--db", type=Path, default=Path("results.sqlite3"))
    run.add_argument("--workers", type=int, default=2)
    run.add_argument("--filter", choices=("lowpass", "highpass"))
    run.add_argument("--cutoff-hz", type=float)
    run.add_argument("--order", type=int, default=4)
    run.add_argument("--max-peaks", type=int, default=5)
    history = commands.add_parser("history", help="read saved runs or one run's file outcomes")
    history.add_argument("--db", type=Path, default=Path("results.sqlite3"))
    history.add_argument("--run-id")
    args = parser.parse_args(argv)

    try:
        if args.command == "history":
            if not args.db.is_file():
                raise FileNotFoundError(f"history database does not exist: {args.db}")
            with ResultStore(args.db) as store:
                data = (
                    {"run": store.get_run(args.run_id), "files": store.list_results(args.run_id)}
                    if args.run_id is not None else {"runs": store.list_runs()}
                )
                print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if (args.filter is None) != (args.cutoff_hz is None):
            parser.error("--filter and --cutoff-hz must be supplied together")
        if args.workers < 1:
            parser.error("--workers must be a positive integer")
        filter_config = None if args.filter is None else FilterConfig(args.filter, args.cutoff_hz, args.order)
        peak_config = PeakConfig(max_peaks=args.max_peaks)
        jobs = [FileJob(f"file-{index}", path) for index, path in enumerate(args.paths, 1)]
        with ResultStore(args.db) as store:
            run_id = store.create_run(
                expected_count=len(jobs), worker_count=min(args.workers, len(jobs)),
                filter_config=filter_config, peak_config=peak_config,
            )
            _print({"event": "run_started", "run_id": run_id, "total": len(jobs)})
            try:
                with closing(iter_batch(
                    jobs, worker_count=args.workers, filter_config=filter_config, peak_config=peak_config,
                )) as results:
                    for result in results:
                        result_id = store.save_result(run_id, result)
                        _print({
                            "event": "file_completed", "source_id": result.source_id,
                            "result_id": result_id,
                            "status": "succeeded" if result.succeeded else "failed",
                            "error_code": None if result.error is None else result.error.error_code,
                        })
                store.finish_run(run_id)
            except BaseException as exc:
                try:
                    store.finish_run(run_id, error_message=f"{type(exc).__name__}: {exc}")
                except (sqlite3.Error, OSError, ValueError, RuntimeError):
                    print("Could not mark the interrupted run as failed.", file=sys.stderr)
                raise
            summary = store.get_run(run_id)
            _print({"event": "run_finished", **summary})
            return 1 if summary["failure_count"] else 0
    except KeyboardInterrupt:
        print("Analysis interrupted.", file=sys.stderr)
        return 130
    except (sqlite3.Error, OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
