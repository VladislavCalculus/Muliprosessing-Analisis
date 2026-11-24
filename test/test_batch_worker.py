"""MLT-21: real per-file pipeline and the serializable process boundary."""

from dataclasses import FrozenInstanceError, fields
from pathlib import Path
import pickle
import wave

import numpy as np
import pytest

from audio_contracts import FileJob, JobError
from batch_proc import JobResult, process_file
import batch_proc.worker as worker
from signal_proc import FilterConfig


def write_tone(path: Path) -> Path:
    samples = np.rint(16_384 * np.sin(2 * np.pi * 440 * np.arange(8_000) / 8_000))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(samples.astype("<i2").tobytes())
    return path


def test_file_job_is_small_immutable_and_pickle_compatible(tmp_path: Path) -> None:
    job = FileJob("job-1", tmp_path / "not-created.wav", "selected.wav")
    assert pickle.loads(pickle.dumps(job)) == job
    assert job.path.is_absolute()
    assert {field.name for field in fields(job)} == {
        "source_id", "path", "source_name", "schema_version"
    }
    with pytest.raises(FrozenInstanceError):
        job.source_id = "changed"
    for source_id, path in [("", tmp_path / "x"), ("valid", "")]:
        with pytest.raises(ValueError):
            FileJob(source_id, path)
    with pytest.raises(ValueError, match="schema"):
        FileJob("valid", "x.wav", schema_version=True)


def test_process_file_preserves_identity_audio_and_source_file(tmp_path: Path) -> None:
    path = write_tone(tmp_path / "tone.wav")
    original = path.read_bytes()
    result = process_file(FileJob("tone-1", path, "display.wav"))
    restored = pickle.loads(pickle.dumps(result))

    assert result.succeeded
    assert result.error is None
    assert result.source_id == "tone-1"
    assert result.packet.source_name == "display.wav"
    assert result.packet.frame_count == 8_000
    assert result.packet.peaks_by_channel[0][0].frequency_hz == pytest.approx(440)
    assert result.worker_pid > 0 and result.elapsed_seconds >= 0
    np.testing.assert_array_equal(restored.packet.samples, result.packet.samples)
    assert path.read_bytes() == original


def test_file_errors_are_correlated_and_do_not_prevent_next_job(tmp_path: Path) -> None:
    bad = process_file(FileJob("missing-1", tmp_path / "missing.wav"))
    path = write_tone(tmp_path / "tone.wav")
    invalid_filter = process_file(
        FileJob("bad-cutoff", path), filter_config=FilterConfig("lowpass", 4_000)
    )
    following = process_file(FileJob("last", path))

    assert bad.error.stage == "read"
    assert bad.error.error_code == "read_failed"
    assert bad.error.source_id == "missing-1"
    assert invalid_filter.error.stage == "process"
    assert invalid_filter.error.error_code == "processing_failed"
    assert "Nyquist" in invalid_filter.error.message
    assert following.succeeded and following.source_id == "last"
    assert pickle.loads(pickle.dumps(bad)).error == bad.error


def test_worker_validates_caller_and_isolates_unexpected_dsp_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_dsp(*args, **kwargs):
        raise RuntimeError("controlled DSP failure")

    path = write_tone(tmp_path / "tone.wav")
    job = FileJob("failure", path)
    monkeypatch.setattr(worker, "process_signal", broken_dsp)
    result = process_file(job)
    assert result.error == JobError(
        "failure", "processing_failed", "RuntimeError: controlled DSP failure", "process", "tone.wav"
    )
    with pytest.raises(TypeError, match="FileJob"):
        process_file(str(path))
    with pytest.raises(TypeError, match="FilterConfig"):
        process_file(job, filter_config={})
    with pytest.raises(ValueError, match="exactly one"):
        JobResult(job, None, None, 1, 0)
