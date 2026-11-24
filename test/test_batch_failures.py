"""MLT-29: аварія worker-а ізольована від інших активних і наступних задач."""

import multiprocessing as mp
import os
from pathlib import Path
import pickle
import time
import wave

import numpy as np

from audio_contracts import FileJob
from batch_proc import WorkerPool, iter_batch, process_file


def make_tone(path: Path) -> Path:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        samples = 16_384 * np.sin(2 * np.pi * 440 * np.arange(800) / 8_000)
        stream.writeframes(samples.astype("<i2").tobytes())
    return path


def wait_for(path: Path) -> None:
    deadline = time.monotonic() + 15
    while not path.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("test coordination deadline exceeded")
        time.sleep(0.01)


def crashing_processor(job, **kwargs):
    started = job.path.parent / "survivor-started"
    if job.source_id == "crash":
        wait_for(started)
        os._exit(23)
    if job.source_id == "survivor":
        started.write_text(str(os.getpid()))
        wait_for(job.path.parent / "release-survivor")
    return process_file(job, **kwargs)


def test_abrupt_exit_preserves_active_worker_and_processes_pending_files(tmp_path: Path) -> None:
    path = make_tone(tmp_path / "tone.wav")
    jobs = [FileJob(source_id, path) for source_id in ["crash", "survivor", "later-1", "later-2"]]
    iterator = iter_batch(jobs, worker_count=2, _processor=crashing_processor)
    try:
        crashed = next(iterator)
        assert crashed.source_id == "crash" and not crashed.succeeded
        assert crashed.error.stage == "worker" and crashed.error.error_code == "worker_exited"
        assert "23" in crashed.error.message
        assert pickle.loads(pickle.dumps(crashed)).error == crashed.error
        survivor_pid = int((tmp_path / "survivor-started").read_text())
        (tmp_path / "release-survivor").touch()
        remaining = list(iterator)
        assert len(remaining) == 3
        outcomes = {result.source_id: result for result in remaining}
        assert set(outcomes) == {"survivor", "later-1", "later-2"}
        assert all(result.succeeded for result in remaining)
        assert outcomes["survivor"].worker_pid == survivor_pid
        assert outcomes["later-1"].worker_pid not in {survivor_pid, crashed.worker_pid}
    finally:
        iterator.close()


def test_idle_worker_death_does_not_lose_an_unassigned_descriptor(monkeypatch, tmp_path: Path) -> None:
    path = make_tone(tmp_path / "tone.wav")
    original_submit = WorkerPool.submit
    killed = []

    def kill_before_first_assignment(pool, job, *, worker_id=None):
        if not killed:
            worker = pool._workers[worker_id]
            worker.process.kill()
            worker.process.join(timeout=2)
            killed.append(worker.pid)
        return original_submit(pool, job, worker_id=worker_id)

    monkeypatch.setattr(WorkerPool, "submit", kill_before_first_assignment)
    jobs = [FileJob(source_id, path) for source_id in ["first", "second", "third"]]
    results = list(iter_batch(jobs, worker_count=2))
    assert len(results) == 3
    assert {result.source_id for result in results} == {job.source_id for job in jobs}
    assert all(result.succeeded for result in results)
    assert all(result.worker_pid not in killed for result in results)


def test_closing_after_crash_cleans_survivor_and_replacement(tmp_path: Path) -> None:
    path = make_tone(tmp_path / "tone.wav")
    previous = {process.pid for process in mp.active_children()}
    iterator = iter_batch(
        [FileJob(source_id, path) for source_id in ["crash", "survivor", "pending"]],
        worker_count=2, _processor=crashing_processor,
    )
    try:
        assert next(iterator).error.error_code == "worker_exited"
    finally:
        iterator.close()
    assert {process.pid for process in mp.active_children()} <= previous
