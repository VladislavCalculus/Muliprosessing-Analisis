"""MLT-19: розподіл реальних WAV та кореляція незалежно від порядку завершення."""

from pathlib import Path
import time
import wave

import numpy as np
import pytest

from audio_contracts import FileJob
from batch_proc import iter_batch, process_file
from batch_proc.pool import WorkerPool


def make_tone(path: Path) -> Path:
    samples = 16_384 * np.sin(2 * np.pi * 440 * np.arange(800) / 8_000)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(samples.astype("<i2").tobytes())
    return path


def ordered_processor(job, **kwargs):
    if job.source_id == "first":
        release = job.path.parent / "release-first"
        deadline = time.monotonic() + 15
        while not release.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("test did not release the first job")
            time.sleep(0.01)
    return process_file(job, **kwargs)


def test_completion_order_is_independent_of_input_order(tmp_path: Path) -> None:
    path = make_tone(tmp_path / "tone.wav")
    results = iter_batch(
        [FileJob("first", path), FileJob("second", path)],
        worker_count=2,
        _processor=ordered_processor,
    )
    try:
        second = next(results)
        assert second.source_id == "second" and second.succeeded
        (tmp_path / "release-first").touch()
        first = next(results)
        assert first.source_id == "first" and first.succeeded
        assert first.worker_pid != second.worker_pid
        assert first.packet.peaks_by_channel[0][0].frequency_hz == pytest.approx(440)
        assert list(results) == []
    finally:
        results.close()


def test_read_error_does_not_drop_a_later_pending_file(tmp_path: Path) -> None:
    path = make_tone(tmp_path / "tone.wav")
    jobs = [
        FileJob("good-first", path),
        FileJob("bad-middle", tmp_path / "missing.wav"),
        FileJob("good-last", path),
    ]
    results = {result.source_id: result for result in iter_batch(jobs, worker_count=2)}
    assert set(results) == {job.source_id for job in jobs}
    assert results["good-first"].succeeded
    assert results["bad-middle"].error.error_code == "read_failed"
    assert results["good-last"].succeeded


def test_all_descriptors_are_validated_before_starting_any_worker(monkeypatch, tmp_path: Path) -> None:
    def unexpected_start(pool):
        raise AssertionError("validation must precede process creation")

    monkeypatch.setattr(WorkerPool, "start", unexpected_start)
    assert list(iter_batch([], worker_count=2)) == []
    with pytest.raises(ValueError, match="unique"):
        list(iter_batch([FileJob("same", tmp_path / "a"), FileJob("same", tmp_path / "b")]))
    with pytest.raises(TypeError, match="FileJob"):
        list(iter_batch([FileJob("valid", tmp_path / "a"), object()]))
    with pytest.raises(ValueError, match="positive integer"):
        list(iter_batch([], worker_count=0))
