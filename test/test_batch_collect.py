"""MLT-20: повні результати й помилки збираються в головному процесі."""

import multiprocessing as mp
from os import getpid
from pathlib import Path
import wave

import numpy as np
import pytest

from audio_contracts import FileJob
from batch_proc import run_batch
from signal_proc import FilterConfig


def make_tone(path: Path) -> Path:
    samples = 16_384 * np.sin(2 * np.pi * 440 * np.arange(8_000) / 8_000)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(samples.astype("<i2").tobytes())
    return path


def test_parent_collects_full_filtered_packets_peaks_and_correlated_errors(tmp_path: Path) -> None:
    path = make_tone(tmp_path / "tone.wav")
    observed = []

    def on_result(result):
        observed.append((getpid(), result.source_id, result))

    result = run_batch(
        [FileJob("ok", path), FileJob("missing", tmp_path / "missing.wav")],
        worker_count=2,
        filter_config=FilterConfig("lowpass", 600),
        on_result=on_result,
    )
    assert result.total_count == 2 and result.success_count == 1 and result.failure_count == 1
    assert result.parent_pid == getpid() and result.elapsed_seconds > 0
    assert len(result.worker_pids) == 2 and getpid() not in result.worker_pids
    assert set(result.results_by_source) == {"ok", "missing"}
    good = result.results_by_source["ok"].packet
    assert good.samples.shape == (8_000, 1)
    assert good.spectrum.amplitudes.shape == (4_001, 1)
    assert good.spectrum.frequencies_hz.shape == (4_001,)
    assert good.filter_config == FilterConfig("lowpass", 600)
    assert good.peaks_by_channel[0][0].frequency_hz == pytest.approx(440)
    assert result.results_by_source["missing"].error.error_code == "read_failed"
    assert {source_id for _, source_id, _ in observed} == {"ok", "missing"}
    assert all(pid == getpid() for pid, _, _ in observed)
    for _, source_id, outcome in observed:
        assert outcome is result.results_by_source[source_id]


def test_callback_failure_propagates_after_child_cleanup(tmp_path: Path) -> None:
    path = make_tone(tmp_path / "tone.wav")
    previous = {process.pid for process in mp.active_children()}

    def fail_to_store(result):
        raise OSError("controlled storage failure")

    with pytest.raises(OSError, match="controlled storage failure"):
        run_batch(
            [FileJob("first", path), FileJob("second", path)],
            worker_count=2, on_result=fail_to_store,
        )
    assert {process.pid for process in mp.active_children()} <= previous


def test_empty_aggregate_has_no_workers_or_callbacks() -> None:
    observed = []
    result = run_batch([], on_result=observed.append)
    assert result.results_by_source == {}
    assert result.total_count == result.success_count == result.failure_count == 0
    assert result.worker_pids == () and observed == []
