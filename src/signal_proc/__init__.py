"""Public API for the MLT-5 signal-processing stage."""

from .processing import (
    FilterConfig,
    PeakConfig,
    SignalPacket,
    SignalSpectrum,
    SpectralPeak,
    process_signal,
)

__all__ = [
    "FilterConfig",
    "PeakConfig",
    "SignalPacket",
    "SignalSpectrum",
    "SpectralPeak",
    "process_signal",
]

