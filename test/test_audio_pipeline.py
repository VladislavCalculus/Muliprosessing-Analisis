"""End-to-end tests over the real loopback HTTP transport."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
import wave

import numpy as np
import pytest

from audio_pipeline import analyze_file, make_server


@pytest.fixture
def pipeline_url() -> Iterator[str]:
    server = make_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _write_tone(path: Path, frequency_hz: float, sample_rate_hz: int = 8_000) -> Path:
    time = np.arange(sample_rate_hz, dtype=np.float64) / sample_rate_hz
    samples = np.rint(16_384 * np.sin(2 * np.pi * frequency_hz * time)).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate_hz)
        output.writeframes(samples.tobytes())
    return path


def test_http_upload_runs_wav_reader_and_signal_processor(
    tmp_path: Path, pipeline_url: str
) -> None:
    wav_path = _write_tone(tmp_path / "tone-440.wav", 440)

    status, payload = analyze_file(
        wav_path,
        server_url=pipeline_url,
        source_id="integration-440",
        filter_kind="lowpass",
        cutoff_hz=1_200,
        filter_order=3,
    )

    assert status == 200
    assert payload["ok"] is True
    assert payload["source_id"] == "integration-440"
    assert payload["audio"] == {
        "sample_rate_hz": 8_000,
        "frame_count": 8_000,
        "channel_count": 1,
        "duration_seconds": 1.0,
        "bits_per_sample": 16,
        "encoding": "PCM",
    }
    assert payload["analysis"]["peaks_by_channel"][0][0]["frequency_hz"] == pytest.approx(
        440.0, abs=1.0
    )
    assert payload["analysis"]["filter"] == {
        "kind": "lowpass",
        "cutoff_hz": 1_200,
        "order": 3,
    }


def test_http_upload_returns_structured_error_for_invalid_wav(
    tmp_path: Path, pipeline_url: str
) -> None:
    invalid_path = tmp_path / "broken.wav"
    invalid_path.write_bytes(b"not a RIFF/WAVE file")

    status, payload = analyze_file(
        invalid_path, server_url=pipeline_url, source_id="integration-broken"
    )

    assert status == 422
    assert payload["ok"] is False
    assert payload["error"]["source_id"] == "integration-broken"
    assert payload["error"]["error_code"] == "invalid_wav"


def test_http_upload_returns_empty_audio_for_zero_byte_file(
    tmp_path: Path, pipeline_url: str
) -> None:
    empty_path = tmp_path / "empty.wav"
    empty_path.write_bytes(b"")

    status, payload = analyze_file(
        empty_path, server_url=pipeline_url, source_id="integration-empty"
    )

    assert status == 422
    assert payload["ok"] is False
    assert payload["error"]["source_id"] == "integration-empty"
    assert payload["error"]["error_code"] == "empty_audio"


def test_loopback_server_handles_concurrent_files_with_distinct_ids(
    tmp_path: Path, pipeline_url: str
) -> None:
    inputs = [
        (_write_tone(tmp_path / "tone-220.wav", 220), "tone-220", 220.0),
        (_write_tone(tmp_path / "tone-660.wav", 660), "tone-660", 660.0),
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda item: analyze_file(
                    item[0], server_url=pipeline_url, source_id=item[1]
                ),
                inputs,
            )
        )

    for (wav_path, expected_source_id, expected_frequency), (status, payload) in zip(
        inputs, results, strict=True
    ):
        assert wav_path.is_file()
        assert status == 200
        assert payload["ok"] is True
        assert payload["source_id"] == expected_source_id
        actual_frequency = payload["analysis"]["peaks_by_channel"][0][0][
            "frequency_hz"
        ]
        assert actual_frequency == pytest.approx(expected_frequency, abs=1.0)
