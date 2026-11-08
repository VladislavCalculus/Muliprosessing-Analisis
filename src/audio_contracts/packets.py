"""Typed, picklable messages at the audio-file and DSP module boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class AudioPacket:
    """One successfully decoded audio source, ready for signal processing.

    ``samples`` is canonicalized to ``(frames, channels)`` and C-contiguous.
    Integer samples retain their source PCM scale; float samples retain their
    amplitude scale. Consumers must treat the array as read-only after packet
    creation, especially once it has been submitted to a process queue.
    """

    source_id: str
    sample_rate_hz: int
    samples: NDArray[Any]
    source_name: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, (int, np.integer))
            or self.schema_version != 1
        ):
            raise ValueError("unsupported AudioPacket schema_version")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be a non-empty string")
        if self.source_name is not None and (
            not isinstance(self.source_name, str) or not self.source_name.strip()
        ):
            raise ValueError("source_name must be None or a non-empty string")
        if (
            isinstance(self.sample_rate_hz, bool)
            or not isinstance(self.sample_rate_hz, (int, np.integer))
            or self.sample_rate_hz <= 0
        ):
            raise ValueError("sample_rate_hz must be a positive integer")

        samples = np.asarray(self.samples)
        if samples.ndim == 1:
            samples = samples[:, np.newaxis]
        if samples.ndim != 2 or samples.shape[0] == 0 or samples.shape[1] == 0:
            raise ValueError(
                "samples must contain frames in shape (frames,) or (frames, channels)"
            )
        if samples.dtype.kind not in "iuf":
            raise TypeError("samples must contain integer PCM or floating-point values")
        if samples.dtype.kind == "f" and not np.isfinite(samples).all():
            raise ValueError("samples must contain only finite values")

        # Make layout predictable without copying arrays that are already C-contiguous.
        samples = np.ascontiguousarray(samples)
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "sample_rate_hz", int(self.sample_rate_hz))

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
        """Return the versioned envelope; ``samples`` remains a NumPy array."""

        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "sample_rate_hz": self.sample_rate_hz,
            "frame_count": self.frame_count,
            "channel_count": self.channel_count,
            "duration_seconds": self.duration_seconds,
            "samples": self.samples,
        }


@dataclass(frozen=True, slots=True)
class AudioReadError:
    """Per-source read failure; the batch coordinator can continue other files."""

    source_id: str
    error_code: str
    message: str
    source_name: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, (int, np.integer))
            or self.schema_version != 1
        ):
            raise ValueError("unsupported AudioReadError schema_version")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be a non-empty string")
        if not isinstance(self.error_code, str) or not self.error_code.strip():
            raise ValueError("error_code must be a non-empty string")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message must be a non-empty string")
        if self.source_name is not None and (
            not isinstance(self.source_name, str) or not self.source_name.strip()
        ):
            raise ValueError("source_name must be None or a non-empty string")

    def to_payload(self) -> dict[str, Any]:
        """Return a small, JSON-compatible error envelope."""

        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "error_code": self.error_code,
            "message": self.message,
        }


AudioReadResult: TypeAlias = AudioPacket | AudioReadError
