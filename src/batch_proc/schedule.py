"""Bounded file scheduling over the reusable worker pool."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Iterator

from audio_contracts import FileJob, JobError
from signal_proc import FilterConfig, PeakConfig

from .pool import WorkerExitedError, WorkerPool
from .worker import JobResult, process_file


def validate_jobs(jobs: Iterable[FileJob]) -> tuple[FileJob, ...]:
    """Snapshot finite lightweight descriptors and reject ambiguous identity."""

    prepared = tuple(jobs)
    seen: set[str] = set()
    for job in prepared:
        if not isinstance(job, FileJob):
            raise TypeError("jobs must contain FileJob objects")
        if job.source_id in seen:
            raise ValueError("source_id must be unique within a batch")
        seen.add(job.source_id)
    return prepared


def iter_batch(
    jobs: Iterable[FileJob],
    *,
    worker_count: int = 2,
    filter_config: FilterConfig | None = None,
    peak_config: PeakConfig | None = None,
    _processor: Callable[..., JobResult] = process_file,
) -> Iterator[JobResult]:
    """Yield each file outcome as it completes, without retaining audio arrays.

    The first iteration validates the entire finite descriptor set before any
    worker starts. At most worker_count files are assigned at once. Completion
    order is not input order: use source_id for correlation. Close the iterator
    explicitly when abandoning iteration, or use contextlib.closing.
    """

    prepared = validate_jobs(jobs)
    if type(worker_count) is not int or worker_count < 1:
        raise ValueError("worker_count must be a positive integer")
    # Construct even for empty input to apply the same options validation.
    pool = WorkerPool(
        min(worker_count, len(prepared)) if prepared else worker_count,
        filter_config=filter_config,
        peak_config=peak_config,
        _processor=_processor,
    )
    if not prepared:
        pool.close()
        return
    pending = deque(prepared)
    restarts = 0

    def recover(error: WorkerExitedError) -> JobResult | None:
        nonlocal restarts
        restart = bool(pending)
        if restart:
            restarts += 1
            if restarts > len(prepared) + worker_count:
                raise RuntimeError("worker restart limit exceeded") from error
        pool.recover_worker(error.worker_id, restart=restart)
        if error.job is None:
            return None
        return JobResult(
            error.job, None,
            JobError(
                error.job.source_id, "worker_exited", str(error), "worker",
                error.job.source_name or error.job.path.name or None,
            ),
            error.worker_pid, error.elapsed_seconds,
        )

    with pool:
        while pending or pool.active_count:
            for worker_id in pool.idle_worker_ids:
                if not pending:
                    break
                job = pending[0]
                try:
                    pool.submit(job, worker_id=worker_id)
                except WorkerExitedError as error:
                    if error.job is not None:
                        # send() may fail after assignment; count that job once.
                        pending.popleft()
                    result = recover(error)
                    if result is not None:
                        yield result
                else:
                    pending.popleft()
            if not pool.active_count:
                continue
            try:
                result = pool.receive()
            except WorkerExitedError as error:
                result = recover(error)
            if result is not None:
                yield result
