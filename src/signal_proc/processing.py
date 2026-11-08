"""Filtering, FFT and peak detection for one decoded audio packet.

This module does not read or write files, which keeps it independent of the WAV
reader and worker orchestration stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy import fft, signal

from audio_contracts import AudioPacket


@dataclass(frozen=True)
class FilterConfig:
    """Butterworth filter settings; cutoff is expressed in Hz."""

    kind: Literal["lowpass", "highpass"]
    cutoff_hz: float
    order: int = 4

    def __post_init__(self) -> None:
        if self.kind not in ("lowpass", "highpass"):
            raise ValueError("filter kind must be 'lowpass' or 'highpass'")
        if not isfinite(self.cutoff_hz) or self.cutoff_hz <= 0:
            raise ValueError("cutoff_hz must be a positive finite number")
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 1:
            raise ValueError("filter order must be a positive integer")


@dataclass(frozen=True)
class PeakConfig:
    """Rules for selecting prominent frequencies from each channel spectrum."""

    max_peaks: int = 5
    min_amplitude_ratio: float = 0.05
    min_frequency_hz: float = 0.0
    min_separation_hz: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.max_peaks, bool) or not isinstance(self.max_peaks, int) or self.max_peaks < 1:
            raise ValueError("max_peaks must be a positive integer")
        if not isfinite(self.min_amplitude_ratio) or not 0 <= self.min_amplitude_ratio <= 1:
            raise ValueError("min_amplitude_ratio must be between 0 and 1")
        if not isfinite(self.min_frequency_hz) or self.min_frequency_hz < 0:
            raise ValueError("min_frequency_hz must be non-negative and finite")
        if not isfinite(self.min_separation_hz) or self.min_separation_hz < 0:
            raise ValueError("min_separation_hz must be non-negative and finite")


@dataclass(frozen=True)
class SpectralPeak:
    """One detected frequency; channel_index is zero based."""

    channel_index: int
    frequency_hz: float
    amplitude: float


@dataclass(frozen=True)
class SignalSpectrum:
    """One-sided amplitude spectrum, with one column per audio channel."""

    frequencies_hz: NDArray[np.float64]  # shape: (frequency_bins,)
    amplitudes: NDArray[np.float64]  # shape: (frequency_bins, channels)
    window: str = "periodic_hann"
    mean_removed: bool = True
    amplitude_scale: str = "one_sided_peak"

    @property
    def bin_width_hz(self) -> float:
        """Frequency resolution of the FFT in Hz."""

        if len(self.frequencies_hz) < 2:
            return 0.0
        return float(self.frequencies_hz[1] - self.frequencies_hz[0])


@dataclass(frozen=True)
class SignalPacket:
    """Versioned output suitable for the next stage or a process queue.

    NumPy arrays and these top-level dataclasses can be serialized with pickle
    by multiprocessing. ``to_payload`` exposes a stable mapping for consumers.
    """

    source_id: str
    sample_rate_hz: int
    samples: NDArray[np.float64]  # filtered (or copied) frames, shape: (frames, channels)
    spectrum: SignalSpectrum
    peaks_by_channel: tuple[tuple[SpectralPeak, ...], ...]
    filter_config: FilterConfig | None
    peak_config: PeakConfig
    source_name: str | None = None
    schema_version: int = 1

    @property
    def frame_count(self) -> int:
        return int(self.samples.shape[0])

    @property
    def channel_count(self) -> int:
        return int(self.samples.shape[1])

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate_hz

    def to_payload(self) -> dict[str, Any]:
        """Return a shallow, plain mapping; array fields remain NumPy arrays.

        Consumers may use this with process queues. Convert or store large arrays
        separately when a JSON transport is required.
        """

        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "sample_rate_hz": self.sample_rate_hz,
            "frame_count": self.frame_count,
            "channel_count": self.channel_count,
            "duration_seconds": self.duration_seconds,
            "samples": self.samples,
            "spectrum": {
                "frequencies_hz": self.spectrum.frequencies_hz,
                "amplitudes": self.spectrum.amplitudes,
                "bin_width_hz": self.spectrum.bin_width_hz,
                "window": self.spectrum.window,
                "mean_removed": self.spectrum.mean_removed,
                "amplitude_scale": self.spectrum.amplitude_scale,
            },
            "peaks_by_channel": [
                [
                    {"frequency_hz": peak.frequency_hz, "amplitude": peak.amplitude}
                    for peak in channel_peaks
                ]
                for channel_peaks in self.peaks_by_channel
            ],
            "filter": (
                None
                if self.filter_config is None
                else {
                    "kind": self.filter_config.kind,
                    "cutoff_hz": self.filter_config.cutoff_hz,
                    "order": self.filter_config.order,
                }
            ),
            "peak_detection": {
                "max_peaks": self.peak_config.max_peaks,
                "min_amplitude_ratio": self.peak_config.min_amplitude_ratio,
                "min_frequency_hz": self.peak_config.min_frequency_hz,
                "min_separation_hz": self.peak_config.min_separation_hz,
            },
        }


def _as_audio_frames(samples: ArrayLike) -> NDArray[np.float64]:
    data = np.asarray(samples)
    if data.ndim == 1:
        data = data[:, np.newaxis]
    if data.ndim != 2 or data.shape[0] == 0 or data.shape[1] == 0:
        raise ValueError("samples must contain frames in shape (frames,) or (frames, channels)")
    if np.issubdtype(data.dtype, np.signedinteger):
        scale = float(np.iinfo(data.dtype).max) + 1.0
        frames = data.astype(np.float64) / scale
    elif np.issubdtype(data.dtype, np.unsignedinteger):
        midpoint = float(np.iinfo(data.dtype).max + 1) / 2.0
        frames = (data.astype(np.float64) - midpoint) / midpoint
    elif np.issubdtype(data.dtype, np.floating):
        frames = data.astype(np.float64, copy=True)
    else:
        raise TypeError("samples must contain integer PCM or floating-point values")
    if not np.isfinite(frames).all():
        raise ValueError("samples must contain only finite values")
    return frames


def _amplitude_spectrum(
    frames: NDArray[np.float64], sample_rate_hz: int
) -> SignalSpectrum:
    frame_count = frames.shape[0]
    # Remove DC and use a periodic Hann window to reduce spectral leakage.
    centered = frames - frames.mean(axis=0, keepdims=True)
    window = signal.windows.hann(frame_count, sym=False)
    window_sum = window.sum()
    if window_sum == 0:  # Protect normalization if a window has no gain.
        window = np.ones(frame_count, dtype=np.float64)
        window_sum = float(frame_count)
    coefficients = fft.rfft(centered * window[:, np.newaxis], axis=0)
    amplitudes = np.abs(coefficients) / window_sum
    if frame_count % 2 == 0:
        amplitudes[1:-1] *= 2.0
    else:
        amplitudes[1:] *= 2.0
    frequencies = fft.rfftfreq(frame_count, d=1.0 / sample_rate_hz)
    return SignalSpectrum(frequencies_hz=frequencies, amplitudes=amplitudes)


def _detect_peaks(
    spectrum: SignalSpectrum, config: PeakConfig
) -> tuple[tuple[SpectralPeak, ...], ...]:
    frequencies = spectrum.frequencies_hz
    amplitudes = spectrum.amplitudes
    result: list[tuple[SpectralPeak, ...]] = []

    for channel_index in range(amplitudes.shape[1]):
        values = amplitudes[:, channel_index].copy()
        values[0] = 0.0  # DC is not a dominant audible frequency.
        in_range = frequencies >= config.min_frequency_hz
        if not in_range.any():
            result.append(())
            continue
        # Threshold against the strongest bin the caller asked us to consider.
        # Peaks outside this frequency range must not suppress eligible peaks.
        maximum = float(values[in_range].max())
        if maximum <= 0:
            result.append(())
            continue
        indices, _ = signal.find_peaks(values)
        # find_peaks omits endpoints; the Nyquist bin can be a valid maximum.
        # Include a tied final plateau too (a Nyquist tone with a periodic Hann
        # window can have equal amplitude in the last two bins).
        if len(values) > 1 and values[-1] >= values[-2]:
            indices = np.append(indices, len(values) - 1)
        threshold = maximum * config.min_amplitude_ratio
        indices = [
            int(index)
            for index in indices
            if in_range[index] and values[index] >= threshold
        ]
        indices.sort(key=lambda index: (-values[index], frequencies[index]))
        selected: list[int] = []
        for index in indices:
            # Enforce physical-frequency separation after range filtering so
            # an out-of-range peak cannot suppress an in-range candidate.
            if all(abs(frequencies[index] - frequencies[prior]) >= config.min_separation_hz for prior in selected):
                selected.append(index)
            if len(selected) == config.max_peaks:
                break
        result.append(
            tuple(
                SpectralPeak(
                    channel_index=channel_index,
                    frequency_hz=float(frequencies[index]),
                    amplitude=float(values[index]),
                )
                for index in selected
            )
        )
    return tuple(result)


def process_signal(
    packet: AudioPacket,
    *,
    filter_config: FilterConfig | None = None,
    peak_config: PeakConfig | None = None,
) -> SignalPacket:
    """Process one decoded audio packet without modifying its input samples.

    Integer PCM is scaled to approximately [-1, 1]; floating-point input keeps
    its amplitude scale. FFT and peaks describe the returned samples, i.e. the
    filtered signal when a filter is configured.
    """

    if not isinstance(packet, AudioPacket):
        raise TypeError("packet must be an AudioPacket")
    if filter_config is not None and not isinstance(filter_config, FilterConfig):
        raise TypeError("filter_config must be a FilterConfig or None")
    if peak_config is not None and not isinstance(peak_config, PeakConfig):
        raise TypeError("peak_config must be a PeakConfig or None")

    sample_rate_hz = packet.sample_rate_hz
    frames = _as_audio_frames(packet.samples)
    if filter_config is not None:
        if filter_config.cutoff_hz >= sample_rate_hz / 2:
            raise ValueError("cutoff_hz must be below the Nyquist frequency")
        sections = signal.butter(
            filter_config.order,
            filter_config.cutoff_hz,
            btype=filter_config.kind,
            fs=sample_rate_hz,
            output="sos",
        )
        frames = signal.sosfilt(sections, frames, axis=0)

    peaks_config = peak_config if peak_config is not None else PeakConfig()
    spectrum = _amplitude_spectrum(frames, int(sample_rate_hz))
    peaks = _detect_peaks(spectrum, peaks_config)
    return SignalPacket(
        source_id=packet.source_id,
        sample_rate_hz=int(sample_rate_hz),
        samples=frames,
        spectrum=spectrum,
        peaks_by_channel=peaks,
        filter_config=filter_config,
        peak_config=peaks_config,
        source_name=packet.source_name,
    )
