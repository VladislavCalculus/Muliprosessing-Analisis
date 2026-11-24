"""A small reusable process pool with one assigned job per worker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import multiprocessing as mp
from multiprocessing.connection import Connection, wait
from time import monotonic

from audio_contracts import FileJob
from signal_proc import FilterConfig, PeakConfig

from .worker import JobResult, process_file


class WorkerExitedError(RuntimeError):
    """An assigned process exited without delivering a complete result."""

    def __init__(
        self, worker_id: int, job: FileJob | None, exitcode: int | None,
        worker_pid: int, elapsed_seconds: float,
    ) -> None:
        self.worker_id = worker_id
        self.job = job
        self.exitcode = exitcode
        self.worker_pid = worker_pid
        self.elapsed_seconds = elapsed_seconds
        super().__init__(f"worker {worker_id} exited without a result (exitcode={exitcode})")


@dataclass
class _Worker:
    process: mp.Process
    connection: Connection
    pid: int
    job: FileJob | None = None
    assigned_at: float | None = None


def _worker_loop(
    connection: Connection,
    filter_config: FilterConfig | None,
    peak_config: PeakConfig | None,
    processor: Callable[..., JobResult],
) -> None:
    try:
        while True:
            job = connection.recv()
            if job is None:
                return
            result = processor(job, filter_config=filter_config, peak_config=peak_config)
            connection.send(result)
    except EOFError:
        return
    finally:
        connection.close()


class WorkerPool:
    """Own bounded reusable workers and their private IPC pipes.

    Use as a context manager or call start()/close() explicitly. Calls belong to
    one parent thread. A worker has at most one assigned FileJob; completed
    packets are received individually. The private processor hook supports
    process-level tests without exposing fault-injection flags in the CLI.
    """

    def __init__(
        self,
        worker_count: int,
        *,
        filter_config: FilterConfig | None = None,
        peak_config: PeakConfig | None = None,
        _processor: Callable[..., JobResult] = process_file,
    ) -> None:
        if type(worker_count) is not int or worker_count < 1:
            raise ValueError("worker_count must be a positive integer")
        if filter_config is not None and not isinstance(filter_config, FilterConfig):
            raise TypeError("filter_config must be a FilterConfig or None")
        if peak_config is not None and not isinstance(peak_config, PeakConfig):
            raise TypeError("peak_config must be a PeakConfig or None")
        if not callable(_processor):
            raise TypeError("_processor must be callable")
        self.worker_count = worker_count
        self.filter_config = filter_config
        self.peak_config = peak_config
        self._processor = _processor
        self._context = mp.get_context("spawn")
        self._workers: dict[int, _Worker] = {}
        self._started = False
        self.closed = False

    def start(self) -> WorkerPool:
        if self.closed:
            raise RuntimeError("pool is closed")
        if self._started:
            return self
        self._started = True
        try:
            for worker_id in range(self.worker_count):
                self._spawn_worker(worker_id)
        except BaseException:
            self.close()
            raise
        return self

    def _spawn_worker(self, worker_id: int) -> None:
        parent, child = self._context.Pipe(duplex=True)
        process = self._context.Process(
            target=_worker_loop,
            args=(child, self.filter_config, self.peak_config, self._processor),
            name=f"mlt-worker-{worker_id}",
        )
        try:
            process.start()
        except BaseException:
            parent.close()
            process.close()
            raise
        finally:
            child.close()
        self._workers[worker_id] = _Worker(process, parent, process.pid)

    @staticmethod
    def _exit_error(worker_id: int, worker: _Worker) -> WorkerExitedError:
        worker.process.join(timeout=0.1)
        elapsed = 0.0 if worker.assigned_at is None else monotonic() - worker.assigned_at
        return WorkerExitedError(worker_id, worker.job, worker.process.exitcode, worker.pid, elapsed)

    def __enter__(self) -> WorkerPool:
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @property
    def worker_pids(self) -> tuple[int, ...]:
        return tuple(worker.pid for worker in self._workers.values())

    @property
    def idle_worker_ids(self) -> tuple[int, ...]:
        return tuple(worker_id for worker_id, worker in self._workers.items() if worker.job is None)

    @property
    def active_count(self) -> int:
        return sum(worker.job is not None for worker in self._workers.values())

    def _require_started(self) -> None:
        if not self._started or self.closed:
            raise RuntimeError("pool must be started and open")

    def submit(self, job: FileJob, *, worker_id: int | None = None) -> int:
        self._require_started()
        if not isinstance(job, FileJob):
            raise TypeError("job must be a FileJob")
        if any(worker.job is not None and worker.job.source_id == job.source_id for worker in self._workers.values()):
            raise ValueError("source_id is already assigned to a worker")
        if worker_id is None:
            if not self.idle_worker_ids:
                raise RuntimeError("all workers already have an assigned job")
            worker_id = self.idle_worker_ids[0]
        if worker_id not in self._workers:
            raise ValueError("unknown worker_id")
        worker = self._workers[worker_id]
        if worker.job is not None:
            raise RuntimeError("worker already has an assigned job")
        if not worker.process.is_alive():
            raise self._exit_error(worker_id, worker)
        worker.job = job
        worker.assigned_at = monotonic()
        try:
            worker.connection.send(job)
        except (OSError, EOFError) as exc:
            raise self._exit_error(worker_id, worker) from exc
        return worker_id

    def receive(self, timeout: float | None = None) -> JobResult | None:
        self._require_started()
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative or None")
        active = [(worker_id, worker) for worker_id, worker in self._workers.items() if worker.job is not None]
        if not active:
            return None
        ready = wait(
            [worker.connection for _, worker in active] + [worker.process.sentinel for _, worker in active],
            timeout,
        )
        for worker_id, worker in active:
            if worker.connection in ready:
                try:
                    result = worker.connection.recv()
                except (EOFError, OSError) as exc:
                    raise self._exit_error(worker_id, worker) from exc
                if not isinstance(result, JobResult) or result.job != worker.job:
                    raise RuntimeError("worker returned a result for an unexpected job")
                worker.job = None
                worker.assigned_at = None
                return result
        for worker_id, worker in active:
            if worker.process.sentinel in ready:
                raise self._exit_error(worker_id, worker)
        return None

    def recover_worker(self, worker_id: int, *, restart: bool) -> None:
        """Reap only the failed worker, optionally replacing its capacity.

        The failed job is never resubmitted here. Its supervisor must emit one
        failure outcome or preserve a descriptor that was not yet assigned.
        """

        self._require_started()
        worker = self._workers[worker_id]
        if worker.process.is_alive():
            worker.process.terminate()
        worker.process.join(timeout=1.0)
        if worker.process.is_alive():
            worker.process.kill()
            worker.process.join(timeout=1.0)
        if worker.process.is_alive():
            raise RuntimeError("failed worker could not be stopped")
        worker.connection.close()
        worker.process.close()
        del self._workers[worker_id]
        if restart:
            self._spawn_worker(worker_id)

    def close(self) -> None:
        """Close within bounded grace periods, terminating unfinished jobs."""

        if self.closed:
            return
        self.closed = True
        for worker in self._workers.values():
            if worker.process.is_alive():
                if worker.job is not None:
                    worker.process.terminate()
                else:
                    try:
                        worker.connection.send(None)
                    except (OSError, EOFError):
                        worker.process.terminate()
        deadline = monotonic() + 2.0
        for worker in self._workers.values():
            worker.process.join(timeout=max(0.0, deadline - monotonic()))
            if worker.process.is_alive():
                worker.process.terminate()
        deadline = monotonic() + 2.0
        for worker in self._workers.values():
            worker.process.join(timeout=max(0.0, deadline - monotonic()))
            if worker.process.is_alive():
                worker.process.kill()
        deadline = monotonic() + 1.0
        for worker in self._workers.values():
            worker.process.join(timeout=max(0.0, deadline - monotonic()))
            worker.connection.close()
            worker.job = None
            if not worker.process.is_alive():
                worker.process.close()
