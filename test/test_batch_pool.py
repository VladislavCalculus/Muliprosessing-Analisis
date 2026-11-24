"""MLT-22: real spawn worker lifecycle and resource cleanup."""

import multiprocessing as mp
from pathlib import Path
import time
import wave

import numpy as np
import pytest

from audio_contracts import FileJob
from batch_proc import WorkerPool, process_file


def slow_processor(job, **kwargs):
    time.sleep(30)
    return process_file(job, **kwargs)


def make_tone(path: Path) -> Path:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        samples = 16_384 * np.sin(2 * np.pi * 440 * np.arange(800) / 8_000)
        stream.writeframes(samples.astype("<i2").tobytes())
    return path


def assert_children_stopped(pids) -> None:
    assert not set(pids).intersection(process.pid for process in mp.active_children())


def test_pool_uses_two_reusable_spawn_processes(tmp_path: Path) -> None:
    path = make_tone(tmp_path / "tone.wav")
    pool = WorkerPool(2)
    with pool:
        pids = pool.worker_pids
        assert len(set(pids)) == 2
        assert mp.current_process().pid not in pids
        assert pool.submit(FileJob("first", path)) == 0
        assert pool.submit(FileJob("second", path)) == 1
        assert pool.active_count == 2
        results = [pool.receive(timeout=20), pool.receive(timeout=20)]
        assert {result.source_id for result in results} == {"first", "second"}
        assert {result.worker_pid for result in results} == set(pids)
        assert all(result.succeeded for result in results)
        assert pool.active_count == 0
        pool.submit(FileJob("third", path), worker_id=0)
        third = pool.receive(timeout=20)
        assert third.succeeded and third.worker_pid == pids[0]
        assert pool.worker_pids == pids
    assert pool.closed and pool.active_count == 0
    assert_children_stopped(pids)


def test_exception_closes_busy_workers_and_rejects_further_submissions(tmp_path: Path) -> None:
    pool = WorkerPool(1, _processor=slow_processor)
    with pytest.raises(RuntimeError, match="caller failed"):
        with pool:
            pids = pool.worker_pids
            pool.submit(FileJob("slow", tmp_path / "unused.wav"))
            raise RuntimeError("caller failed")
    pool.close()
    assert_children_stopped(pids)
    with pytest.raises(RuntimeError, match="started and open"):
        pool.submit(FileJob("after-close", "unused.wav"))


def test_partial_start_failure_cleans_up_already_started_process(monkeypatch) -> None:
    process_type = mp.get_context("spawn").Process
    original_start = process_type.start
    starts = []

    def fail_second(process):
        if starts:
            raise OSError("controlled start failure")
        original_start(process)
        starts.append(process.pid)

    monkeypatch.setattr(process_type, "start", fail_second)
    pool = WorkerPool(2)
    with pytest.raises(OSError, match="controlled start failure"):
        pool.start()
    assert pool.closed
    assert_children_stopped(starts)
