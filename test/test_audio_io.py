"""Основні перевірки MLT-4 на реальних тимчасових WAV-файлах."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from audio_contracts import AudioPacket, AudioReadError
from audio_io import WavFile, WavSource, read_wav, read_wav_batch, read_wav_details
from signal_proc import process_signal


def _write_pcm(path: Path, samples: np.ndarray, sample_rate_hz: int = 8_000) -> Path:
    channels = 1 if samples.ndim == 1 else samples.shape[1]
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate_hz)
        output.writeframes(samples.astype("<i2").tobytes())
    return path


@pytest.mark.parametrize(
    "sample_rate_hz, channels, frame_count, duration_seconds",
    [(8_000, 1, 8_000, 1.0), (16_000, 2, 32_000, 2.0)],
    ids=["mono", "stereo"],
)
def test_wav_parameters(
    tmp_path: Path,
    sample_rate_hz: int,
    channels: int,
    frame_count: int,
    duration_seconds: float,
) -> None:
    samples = np.full(frame_count, 1_000, dtype=np.int16)
    if channels == 2:
        samples = np.column_stack((samples, -samples))
    path = _write_pcm(tmp_path / "recording.wav", samples, sample_rate_hz)

    details = read_wav_details(path, source_id="recording")

    assert isinstance(details, WavFile)
    assert details.packet.sample_rate_hz == sample_rate_hz
    assert details.packet.channel_count == channels
    assert details.packet.duration_seconds == pytest.approx(duration_seconds)
    assert details.bits_per_sample == 16


def test_batch_continues_after_bad_middle_file(tmp_path: Path) -> None:
    first = _write_pcm(tmp_path / "first.wav", np.array([100, -100], dtype=np.int16))
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"This is text, not WAV audio.")
    last_samples = np.array([[10, -10], [20, -20]], dtype=np.int16)
    last = _write_pcm(tmp_path / "last.wav", last_samples, 16_000)

    results = list(
        read_wav_batch(
            [
                WavSource(first, "file-1"),
                WavSource(broken, "file-2"),
                WavSource(last, "file-3"),
            ]
        )
    )

    assert isinstance(results[0], AudioPacket)
    assert isinstance(results[1], AudioReadError)
    assert results[1].error_code == "invalid_wav"
    assert isinstance(results[2], AudioPacket)
    np.testing.assert_array_equal(results[2].samples, last_samples)


def test_empty_file_returns_controlled_error(tmp_path: Path) -> None:
    path = tmp_path / "empty.wav"
    path.write_bytes(b"")

    result = read_wav(path, source_id="empty")

    assert isinstance(result, AudioReadError)
    assert result.error_code == "empty_audio"


def test_missing_file_returns_read_failed(tmp_path: Path) -> None:
    result = read_wav(tmp_path / "missing.wav", source_id="missing")

    assert isinstance(result, AudioReadError)
    assert result.error_code == "read_failed"


def test_decoded_wav_can_be_processed_by_mlt5(tmp_path: Path) -> None:
    time_s = np.arange(8_000, dtype=np.float64) / 8_000
    samples = np.rint(16_384 * np.sin(2 * np.pi * 440 * time_s)).astype(np.int16)
    path = _write_pcm(tmp_path / "tone440.wav", samples)

    packet = read_wav(path, source_id="tone-440")

    assert isinstance(packet, AudioPacket)
    result = process_signal(packet)
    assert result.peaks_by_channel[0][0].frequency_hz == pytest.approx(440.0, abs=1.0)
