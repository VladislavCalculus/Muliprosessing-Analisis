"""Opt-in in-memory aggregation of correlated worker outcomes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import closing
from dataclasses import dataclass
from math import isfinite
from os import getpid
from time import perf_counter

from audio_contracts import FileJob
from signal_proc import FilterConfig, PeakConfig

from .schedule import iter_batch, validate_jobs
from .worker import JobResult, process_file


@dataclass(frozen=True, slots=True)
class BatchResult:
    """A completed batch retained in its parent process.

    The dictionary and NumPy arrays are shallow data, not deeply immutable.
    Keep outcomes unchanged while sharing them with consumers.
    """

    results_by_source: dict[str, JobResult]
    total_count: int
    parent_pid: int
    elapsed_seconds: float

    def __post_init__(self) -> None:
        if type(self.total_count) is not int or self.total_count != len(self.results_by_source):
            raise ValueError("total_count must match the number of outcomes")
        if any(not isinstance(value, JobResult) or key != value.source_id for key, value in self.results_by_source.items()):
            raise ValueError("results must be keyed by their source_id")
        if type(self.parent_pid) is not int or self.parent_pid <= 0:
            raise ValueError("parent_pid must be a positive integer")
        if not isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be finite and non-negative")
        object.__setattr__(self, "results_by_source", dict(self.results_by_source))

    @property
    def success_count(self) -> int:
        return sum(result.succeeded for result in self.results_by_source.values())

    @property
    def failure_count(self) -> int:
        return self.total_count - self.success_count

    @property
    def worker_pids(self) -> tuple[int, ...]:
        return tuple(sorted({result.worker_pid for result in self.results_by_source.values()}))


def run_batch(
    jobs: Iterable[FileJob],
    *,
    worker_count: int = 2,
    filter_config: FilterConfig | None = None,
    peak_config: PeakConfig | None = None,
    on_result: Callable[[JobResult], None] | None = None,
    _processor: Callable[..., JobResult] = process_file,
) -> BatchResult:
    """Collect full packets/errors keyed by source_id in the calling process.

    This convenience API retains all arrays. Prefer iter_batch for large inputs.
    on_result runs synchronously in the parent after each outcome arrives; its
    exception propagates after pool cleanup, never becoming a hidden file error.
    """

    if on_result is not None and not callable(on_result):
        raise TypeError("on_result must be callable or None")
    prepared = validate_jobs(jobs)
    started = perf_counter()
    results: dict[str, JobResult] = {}
    iterator = iter_batch(
        prepared,
        worker_count=worker_count,
        filter_config=filter_config,
        peak_config=peak_config,
        _processor=_processor,
    )
    with closing(iterator):
        for result in iterator:
            results[result.source_id] = result
            if on_result is not None:
                on_result(result)
    return BatchResult(results, len(prepared), getpid(), perf_counter() - started)
