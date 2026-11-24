"""Run the existing WAV reader and DSP in the same worker process."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from os import getpid
from time import perf_counter

from audio_contracts import AudioReadError, FileJob, JobError
from audio_io import read_wav
from signal_proc import FilterConfig, PeakConfig, SignalPacket, process_signal


@dataclass(frozen=True, slots=True)
class JobResult:
    """Exactly one success or failure, correlated by the original descriptor.

    Success packets retain NumPy arrays and are intended for trusted local IPC,
    not JSON transport. Exceptions and open file handles never enter the result.
    """

    job: FileJob
    packet: SignalPacket | None
    error: JobError | None
    worker_pid: int
    elapsed_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.job, FileJob):
            raise TypeError("job must be a FileJob")
        if (self.packet is None) == (self.error is None):
            raise ValueError("exactly one of packet or error is required")
        if self.packet is not None and not isinstance(self.packet, SignalPacket):
            raise TypeError("packet must be a SignalPacket or None")
        if self.error is not None and not isinstance(self.error, JobError):
            raise TypeError("error must be a JobError or None")
        payload = self.packet if self.packet is not None else self.error
        if payload.source_id != self.job.source_id:
            raise ValueError("result source_id must match its job")
        if type(self.worker_pid) is not int or self.worker_pid <= 0:
            raise ValueError("worker_pid must be a positive integer")
        if not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be finite and non-negative")

    @property
    def source_id(self) -> str:
        return self.job.source_id

    @property
    def succeeded(self) -> bool:
        return self.packet is not None


def process_file(
    job: FileJob,
    *,
    filter_config: FilterConfig | None = None,
    peak_config: PeakConfig | None = None,
) -> JobResult:
    """Read and process one WAV without modifying it.

    Invalid caller types raise before any read. Ordinary per-file failures are
    returned as JobError, so a coordinator can continue with another descriptor.
    Abrupt process termination must be detected by the future parent supervisor.
    """

    if not isinstance(job, FileJob):
        raise TypeError("job must be a FileJob")
    if filter_config is not None and not isinstance(filter_config, FilterConfig):
        raise TypeError("filter_config must be a FilterConfig or None")
    if peak_config is not None and not isinstance(peak_config, PeakConfig):
        raise TypeError("peak_config must be a PeakConfig or None")
    started = perf_counter()

    def failed(code: str, message: str, stage: str, name: str | None) -> JobResult:
        return JobResult(
            job, None, JobError(job.source_id, code, message, stage, name),
            getpid(), perf_counter() - started,
        )

    try:
        decoded = read_wav(job.path, source_id=job.source_id, source_name=job.source_name)
    except Exception as exc:
        return failed("read_failed", f"{type(exc).__name__}: {exc}", "read", job.source_name)
    if isinstance(decoded, AudioReadError):
        return failed(decoded.error_code, decoded.message, "read", decoded.source_name)
    try:
        packet = process_signal(decoded, filter_config=filter_config, peak_config=peak_config)
    except Exception as exc:
        return failed("processing_failed", f"{type(exc).__name__}: {exc}", "process", decoded.source_name)
    return JobResult(job, packet, None, getpid(), perf_counter() - started)
