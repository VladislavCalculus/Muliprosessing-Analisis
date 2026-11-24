"""Parent-owned SQLite metadata and managed NumPy result artifacts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from importlib.resources import files
import json
from os import getpid, replace
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile
from uuid import uuid4

import numpy as np

from audio_contracts import FileJob, JobError
from batch_proc import JobResult
from signal_proc import FilterConfig, PeakConfig, SignalPacket, SignalSpectrum, SpectralPeak


def _config_json(config) -> str | None:
    return None if config is None else json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))


class ResultStore:
    """Own one SQLite connection in the creating process/thread.

    Metadata and peaks live in SQLite. Successful full numerical packets are
    stored in unique, non-pickle NPZ files beside the database by default.
    """

    def __init__(self, path: str | Path, *, artifact_dir: str | Path | None = None) -> None:
        if sqlite3.sqlite_version_info < (3, 37, 0):
            raise RuntimeError("result store requires SQLite >= 3.37 for STRICT tables")
        if str(path) == ":memory:":
            raise ValueError("ResultStore requires a file-backed database")
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_dir = (
            Path(artifact_dir).expanduser().resolve() if artifact_dir is not None
            else self.path.with_name(self.path.name + ".artifacts")
        ).resolve()
        self._owner_pid = getpid()
        self._closed = False
        self._connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        try:
            try:
                self._connection.execute("SELECT json_valid('{}')").fetchone()
            except sqlite3.OperationalError as exc:
                raise RuntimeError("result store requires SQLite JSON functions") from exc
            self._connection.execute("PRAGMA foreign_keys = ON")
            if self._connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                raise RuntimeError("SQLite foreign key enforcement could not be enabled")
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            tables = self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if version == 0 and tables:
                raise ValueError("refusing to initialize a non-empty unversioned database")
            if version not in (0, 1):
                raise ValueError(f"unsupported result-store schema version: {version}")
            self._connection.executescript(files("result_store").joinpath("schema.sql").read_text())
        except BaseException:
            self._connection.close()
            self._closed = True
            raise

    @property
    def connection(self) -> sqlite3.Connection:
        if self._closed:
            raise RuntimeError("result store is closed")
        if getpid() != self._owner_pid:
            raise RuntimeError("result store belongs to its creating parent process")
        return self._connection

    def __enter__(self) -> ResultStore:
        self.connection
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self.connection.close()
            self._closed = True

    @contextmanager
    def _transaction(self):
        connection = self.connection
        if connection.in_transaction:
            raise RuntimeError("an external transaction is already active")
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    def create_run(
        self, *, expected_count: int, worker_count: int = 2,
        filter_config: FilterConfig | None = None, peak_config: PeakConfig | None = None,
    ) -> str:
        if type(expected_count) is not int or expected_count < 0:
            raise ValueError("expected_count must be a non-negative integer")
        if type(worker_count) is not int or worker_count < 1:
            raise ValueError("worker_count must be a positive integer")
        if filter_config is not None and not isinstance(filter_config, FilterConfig):
            raise TypeError("filter_config must be a FilterConfig or None")
        if peak_config is not None and not isinstance(peak_config, PeakConfig):
            raise TypeError("peak_config must be a PeakConfig or None")
        run_id = uuid4().hex
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO analysis_run (run_id,expected_count,worker_count,parent_pid,filter_json,peak_json) "
                "VALUES (?,?,?,?,?,?)",
                (run_id, expected_count, worker_count, getpid(), _config_json(filter_config),
                 _config_json(peak_config or PeakConfig())),
            )
        return run_id

    def _write_artifact(self, packet: SignalPacket) -> Path:
        arrays = {
            "samples": np.asarray(packet.samples, dtype=np.float64),
            "frequencies_hz": np.asarray(packet.spectrum.frequencies_hz, dtype=np.float64),
            "amplitudes": np.asarray(packet.spectrum.amplitudes, dtype=np.float64),
        }
        if any(not np.isfinite(array).all() for array in arrays.values()):
            raise ValueError("numerical result arrays must contain only finite values")
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        final = self.artifact_dir / (uuid4().hex + ".npz")
        temporary = None
        try:
            with NamedTemporaryFile(dir=self.artifact_dir, suffix=".npz", prefix=".writing-", delete=False) as stream:
                temporary = Path(stream.name)
                np.savez_compressed(
                    stream, **arrays, window=np.array(packet.spectrum.window),
                    mean_removed=np.array(packet.spectrum.mean_removed),
                    amplitude_scale=np.array(packet.spectrum.amplitude_scale),
                )
            replace(temporary, final)
            return final
        except BaseException:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
            raise

    def save_result(self, run_id: str, result: JobResult) -> int:
        if not isinstance(result, JobResult):
            raise TypeError("result must be a JobResult")
        run = self.get_run(run_id)
        packet, error = result.packet, result.error
        artifact = None
        if packet is not None:
            if type(packet.schema_version) is not int or packet.schema_version != 1:
                raise ValueError("unsupported SignalPacket schema_version")
            if (len(packet.peaks_by_channel) != packet.channel_count
                    or any(peak.channel_index != channel
                           for channel, peaks in enumerate(packet.peaks_by_channel) for peak in peaks)):
                raise ValueError("peak channel identity does not match its packet")
            if (json.loads(_config_json(packet.filter_config) or "null") != json.loads(run["filter_json"] or "null")
                    or json.loads(_config_json(packet.peak_config)) != json.loads(run["peak_json"])):
                raise ValueError("packet configuration does not match its analysis run")
            artifact = self._write_artifact(packet)
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    "INSERT INTO file_result (run_id,source_id,source_path,job_name,source_name,status,"
                    "worker_pid,elapsed_seconds,sample_rate_hz,frame_count,channel_count,artifact_name,"
                    "error_stage,error_code,error_message) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, result.source_id, str(result.job.path), result.job.source_name,
                     packet.source_name if packet is not None else error.source_name,
                     "succeeded" if packet is not None else "failed", result.worker_pid,
                     result.elapsed_seconds, packet.sample_rate_hz if packet is not None else None,
                     packet.frame_count if packet is not None else None,
                     packet.channel_count if packet is not None else None,
                     artifact.name if artifact is not None else None,
                     error.stage if error is not None else None,
                     error.error_code if error is not None else None,
                     error.message if error is not None else None),
                )
                result_id = cursor.lastrowid
                if packet is not None:
                    connection.executemany(
                        "INSERT INTO spectral_peak (result_id,channel_index,peak_index,frequency_hz,amplitude) "
                        "VALUES (?,?,?,?,?)",
                        [(result_id, channel, index, peak.frequency_hz, peak.amplitude)
                         for channel, peaks in enumerate(packet.peaks_by_channel)
                         for index, peak in enumerate(peaks)],
                    )
            return result_id
        except BaseException:
            if artifact is not None:
                artifact.unlink(missing_ok=True)
            raise

    def finish_run(self, run_id: str, *, error_message: str | None = None) -> None:
        self.get_run(run_id)
        with self._transaction() as connection:
            connection.execute(
                "UPDATE analysis_run SET status=?,finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),"
                "error_message=? WHERE run_id=?",
                ("completed" if error_message is None else "failed", error_message, run_id),
            )

    def get_run(self, run_id: str) -> dict:
        row = self.connection.execute("SELECT * FROM run_summary WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown analysis run: {run_id}")
        return dict(row)

    def list_runs(self, limit: int = 20) -> list[dict]:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        return [dict(row) for row in self.connection.execute(
            "SELECT s.* FROM run_summary s JOIN analysis_run r USING (run_id) ORDER BY r.rowid DESC LIMIT ?",
            (limit,),
        )]

    def list_results(self, run_id: str) -> list[dict]:
        self.get_run(run_id)
        rows = self.connection.execute(
            "SELECT *,CAST(frame_count AS REAL)/sample_rate_hz AS duration_seconds "
            "FROM file_result WHERE run_id=? ORDER BY result_id", (run_id,),
        ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["peaks"] = [dict(peak) for peak in self.connection.execute(
                "SELECT channel_index,peak_index,frequency_hz,amplitude FROM spectral_peak "
                "WHERE result_id=? ORDER BY channel_index,peak_index", (row["result_id"],),
            )]
            results.append(item)
        return results

    def load_result(self, result_id: int) -> JobResult:
        row = self.connection.execute(
            "SELECT f.*,r.filter_json,r.peak_json FROM file_result f JOIN analysis_run r USING (run_id) "
            "WHERE f.result_id=?", (result_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown file result: {result_id}")
        job = FileJob(row["source_id"], row["source_path"], row["job_name"])
        if row["status"] == "failed":
            error = JobError(row["source_id"], row["error_code"], row["error_message"], row["error_stage"], row["source_name"])
            return JobResult(job, None, error, row["worker_pid"], row["elapsed_seconds"])
        name = row["artifact_name"]
        if Path(name).name != name:
            raise ValueError("invalid managed artifact name")
        path = (self.artifact_dir / name).resolve()
        if path.parent != self.artifact_dir:
            raise ValueError("artifact path escapes its managed directory")
        with np.load(path, allow_pickle=False) as data:
            samples = data["samples"].copy()
            spectrum = SignalSpectrum(
                data["frequencies_hz"].copy(), data["amplitudes"].copy(),
                str(data["window"].item()), bool(data["mean_removed"].item()), str(data["amplitude_scale"].item()),
            )
        peaks = self.connection.execute(
            "SELECT * FROM spectral_peak WHERE result_id=? ORDER BY channel_index,peak_index", (result_id,),
        ).fetchall()
        packet = SignalPacket(
            row["source_id"], row["sample_rate_hz"], samples, spectrum,
            tuple(tuple(SpectralPeak(channel, peak["frequency_hz"], peak["amplitude"])
                        for peak in peaks if peak["channel_index"] == channel)
                  for channel in range(row["channel_count"])),
            FilterConfig(**json.loads(row["filter_json"])) if row["filter_json"] is not None else None,
            PeakConfig(**json.loads(row["peak_json"])), row["source_name"],
        )
        return JobResult(job, packet, None, row["worker_pid"], row["elapsed_seconds"])
