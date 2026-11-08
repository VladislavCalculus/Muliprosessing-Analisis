"""Ten focused unit tests for the MLT-5 signal-processing module."""

from __future__ import annotations

import pickle
from unittest.mock import Mock

import numpy as np
import pytest

import signal_proc.processing as processing
from audio_contracts import AudioPacket
from signal_proc import FilterConfig, PeakConfig, process_signal
from signal_proc.processing import _as_audio_frames

SAMPLE_RATE = 8_000
FRAME_COUNT = 8_000


def make_packet(samples: np.ndarray, sample_rate_hz: int = SAMPLE_RATE) -> AudioPacket:
    return AudioPacket("unit-test-source", sample_rate_hz, samples)


def sine(frequency_hz: float, amplitude: float, sample_rate_hz: int, frame_count: int) -> np.ndarray:
    time_s = np.arange(frame_count, dtype=np.float64) / sample_rate_hz
    return amplitude * np.sin(2.0 * np.pi * frequency_hz * time_s)


def peak_pairs(result, channel: int = 0) -> list[tuple[float, float]]:
    return [
        (peak.frequency_hz, peak.amplitude)
        for peak in result.peaks_by_channel[channel]
    ]


def assert_peak_pairs_close(
    actual: list[tuple[float, float]], expected: list[tuple[float, float]]
) -> None:
    assert len(actual) == len(expected)
    for actual_peak, expected_peak in zip(actual, expected, strict=True):
        assert actual_peak[0] == pytest.approx(expected_peak[0], abs=1e-10, rel=0.0)
        assert actual_peak[1] == pytest.approx(expected_peak[1], abs=1e-10, rel=0.0)


def amplitude_at(result, frequency_hz: float) -> float:
    index = int(np.argmin(np.abs(result.spectrum.frequencies_hz - frequency_hz)))
    return float(result.spectrum.amplitudes[index, 0])


def test_mlt_frequency_resolution_and_peak_order() -> None:
    sample_rate_hz = 800_000
    frame_count = 800_000

    single_tone = process_signal(
        make_packet(sine(440.0, 1.0, sample_rate_hz, frame_count), sample_rate_hz)
    )
    assert single_tone.spectrum.bin_width_hz == pytest.approx(1.0)
    assert_peak_pairs_close(peak_pairs(single_tone), [(440.0, 1.0)])

    mixed = sine(200.0, 1.0, sample_rate_hz, frame_count) + sine(
        600.0, 0.5, sample_rate_hz, frame_count
    )
    two_tones = process_signal(make_packet(mixed, sample_rate_hz))
    assert_peak_pairs_close(peak_pairs(two_tones)[:2], [(200.0, 1.0), (600.0, 0.5)])


def test_peaks_are_separate_per_channel_and_sorted_by_amplitude() -> None:
    channel_0 = sine(440.0, 0.8, SAMPLE_RATE, FRAME_COUNT) + sine(
        1_000.0, 0.3, SAMPLE_RATE, FRAME_COUNT
    )
    channel_1 = sine(1_000.0, 0.6, SAMPLE_RATE, FRAME_COUNT)

    result = process_signal(make_packet(np.column_stack((channel_0, channel_1))))

    assert result.samples.shape == (FRAME_COUNT, 2)
    assert_peak_pairs_close(peak_pairs(result, 0), [(440.0, 0.8), (1_000.0, 0.3)])
    assert_peak_pairs_close(peak_pairs(result, 1), [(1_000.0, 0.6)])


def test_real_low_and_high_pass_filters_attenuate_stop_band_and_preserve_input() -> None:
    samples = sine(440.0, 0.8, SAMPLE_RATE, FRAME_COUNT) + sine(
        1_000.0, 0.3, SAMPLE_RATE, FRAME_COUNT
    )
    packet = make_packet(samples)
    original = packet.samples.copy()
    cases = (
        (FilterConfig("lowpass", 600.0), 440.0, 1_000.0, 0.65, 0.05),
        (FilterConfig("highpass", 700.0), 1_000.0, 440.0, 0.25, 0.20),
    )

    for config, pass_hz, stop_hz, pass_min, stop_max in cases:
        result = process_signal(packet, filter_config=config)
        assert result.filter_config == config
        assert amplitude_at(result, pass_hz) > pass_min
        assert amplitude_at(result, stop_hz) < stop_max

    np.testing.assert_array_equal(packet.samples, original)


def test_filter_backend_uses_stub_and_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    samples = sine(440.0, 0.5, SAMPLE_RATE, FRAME_COUNT)
    packet = make_packet(samples)
    sos_marker = object()
    filtered_frames = np.zeros((FRAME_COUNT, 1), dtype=np.float64)
    butter_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def butter_stub(*args: object, **kwargs: object) -> object:
        butter_calls.append((args, kwargs))
        return sos_marker

    sosfilt_mock = Mock(return_value=filtered_frames.copy())
    monkeypatch.setattr(processing.signal, "butter", butter_stub)
    monkeypatch.setattr(processing.signal, "sosfilt", sosfilt_mock)

    result = process_signal(
        packet, filter_config=FilterConfig("highpass", 800.0, order=3)
    )

    assert butter_calls == [
        ((3, 800.0), {"btype": "highpass", "fs": SAMPLE_RATE, "output": "sos"})
    ]
    sosfilt_mock.assert_called_once()
    positional, keyword = sosfilt_mock.call_args
    assert positional[0] is sos_marker
    np.testing.assert_array_equal(positional[1], samples[:, np.newaxis])
    assert keyword == {"axis": 0}
    np.testing.assert_array_equal(result.samples, filtered_frames)


def test_signed_and_unsigned_pcm_are_scaled_without_mutating_input() -> None:
    for dtype, amplitude, offset in ((np.int16, 16_384, 0), (np.uint8, 64, 128)):
        encoded = np.rint(
            offset
            + amplitude
            * np.sin(2.0 * np.pi * 440.0 * np.arange(FRAME_COUNT) / SAMPLE_RATE)
        ).astype(dtype)
        original = encoded.copy()

        result = process_signal(make_packet(encoded))

        assert result.samples.dtype == np.float64
        assert peak_pairs(result)[0][0] == pytest.approx(440.0)
        assert peak_pairs(result)[0][1] == pytest.approx(0.5, abs=0.03)
        np.testing.assert_array_equal(encoded, original)


def test_odd_length_fft_has_correct_one_sided_amplitude() -> None:
    frame_count = 801
    bin_index = 110
    frequency_hz = bin_index * SAMPLE_RATE / frame_count
    result = process_signal(
        make_packet(sine(frequency_hz, 0.4, SAMPLE_RATE, frame_count))
    )

    assert result.spectrum.amplitudes.shape == (frame_count // 2 + 1, 1)
    assert result.spectrum.frequencies_hz[bin_index] == pytest.approx(frequency_hz)
    assert result.spectrum.amplitudes[bin_index, 0] == pytest.approx(0.4, abs=1e-12)


def test_nyquist_single_frame_and_silence_edge_cases() -> None:
    nyquist = process_signal(make_packet(np.cos(np.pi * np.arange(FRAME_COUNT))))
    assert_peak_pairs_close(
        peak_pairs(nyquist), [(SAMPLE_RATE / 2, 1.0)]
    )

    single_frame = process_signal(make_packet(np.array([0.75], dtype=np.float64)))
    assert single_frame.spectrum.bin_width_hz == 0.0
    np.testing.assert_array_equal(single_frame.spectrum.amplitudes, np.zeros((1, 1)))
    assert single_frame.peaks_by_channel == ((),)

    silence = process_signal(make_packet(np.zeros(256, dtype=np.float64)))
    np.testing.assert_array_equal(silence.spectrum.amplitudes, np.zeros((129, 1)))
    assert silence.peaks_by_channel == ((),)


def test_peak_threshold_range_separation_and_limit() -> None:
    outside_strong = sine(100.0, 1.0, SAMPLE_RATE, FRAME_COUNT) + sine(
        1_000.0, 0.02, SAMPLE_RATE, FRAME_COUNT
    )
    in_range = process_signal(
        make_packet(outside_strong),
        peak_config=PeakConfig(min_frequency_hz=500.0, min_amplitude_ratio=0.05),
    )
    assert_peak_pairs_close(peak_pairs(in_range), [(1_000.0, 0.02)])

    nearby = sine(500.0, 1.0, SAMPLE_RATE, FRAME_COUNT) + sine(
        505.0, 0.5, SAMPLE_RATE, FRAME_COUNT
    )
    separated = process_signal(
        make_packet(nearby),
        peak_config=PeakConfig(
            min_frequency_hz=503.0, min_amplitude_ratio=0.01, min_separation_hz=10.0
        ),
    )
    assert_peak_pairs_close(peak_pairs(separated), [(505.0, 0.5)])

    limited = process_signal(
        make_packet(sine(440.0, 1.0, SAMPLE_RATE, FRAME_COUNT) + sine(
            1_000.0, 0.25, SAMPLE_RATE, FRAME_COUNT
        )),
        peak_config=PeakConfig(max_peaks=1),
    )
    assert_peak_pairs_close(peak_pairs(limited), [(440.0, 1.0)])


def test_invalid_configs_arguments_and_samples_raise_expected_errors() -> None:
    invalid_filter_configs = (
        {"kind": "bandpass", "cutoff_hz": 500.0},
        {"kind": "lowpass", "cutoff_hz": 0.0},
        {"kind": "highpass", "cutoff_hz": float("inf")},
        {"kind": "lowpass", "cutoff_hz": 500.0, "order": True},
    )
    for config in invalid_filter_configs:
        with pytest.raises(ValueError):
            FilterConfig(**config)

    for config in (
        {"max_peaks": 0},
        {"min_amplitude_ratio": 1.1},
        {"min_frequency_hz": -1.0},
        {"min_separation_hz": float("inf")},
    ):
        with pytest.raises(ValueError):
            PeakConfig(**config)

    packet = make_packet(sine(440.0, 0.8, SAMPLE_RATE, FRAME_COUNT))
    with pytest.raises(TypeError, match="AudioPacket"):
        process_signal(np.zeros(FRAME_COUNT))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="FilterConfig"):
        process_signal(packet, filter_config=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="PeakConfig"):
        process_signal(packet, peak_config=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Nyquist"):
        process_signal(packet, filter_config=FilterConfig("lowpass", SAMPLE_RATE / 2))

    with pytest.raises(ValueError, match="frames"):
        _as_audio_frames(np.array([], dtype=np.float64))
    with pytest.raises(TypeError, match="integer PCM"):
        _as_audio_frames(np.array([True, False]))
    with pytest.raises(ValueError, match="finite"):
        _as_audio_frames(np.array([0.0, np.nan]))


def test_payload_and_pickle_round_trip_preserve_result() -> None:
    packet = make_packet(sine(440.0, 0.8, SAMPLE_RATE, FRAME_COUNT))
    result = process_signal(packet, filter_config=FilterConfig("lowpass", 1_000.0))
    plain = process_signal(packet).to_payload()
    payload = result.to_payload()
    restored = pickle.loads(pickle.dumps(result))

    assert payload["schema_version"] == 1
    assert payload["source_id"] == packet.source_id
    assert payload["filter"] == {"kind": "lowpass", "cutoff_hz": 1_000.0, "order": 4}
    assert payload["spectrum"]["window"] == "periodic_hann"
    assert plain["filter"] is None
    np.testing.assert_array_equal(restored.samples, result.samples)
    np.testing.assert_array_equal(restored.spectrum.amplitudes, result.spectrum.amplitudes)
    assert_peak_pairs_close(peak_pairs(restored), peak_pairs(result))
