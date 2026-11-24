"""Компактні перевірки SQLite на реальних тимчасових базах даних."""

from dataclasses import replace
from importlib.resources import files
from pathlib import Path
import sqlite3

import numpy as np
import pytest
from scipy.io import wavfile

from audio_contracts import FileJob
from batch_proc import process_file
from result_store import ResultStore
from signal_proc import SpectralPeak


def outcome(tmp_path: Path, source_id: str = "tone"):
    path = tmp_path / "tone.wav"
    time_s = np.arange(800, dtype=np.float64) / 8_000
    samples = np.column_stack((2 * np.sin(2 * np.pi * 440 * time_s), 0.3 * np.sin(2 * np.pi * 1_000 * time_s)))
    wavfile.write(path, 8_000, samples.astype(np.float32))
    result = process_file(FileJob(source_id, path))
    assert result.succeeded
    return result


def test_schema_seed_two_master_detail_links_and_sql_functions(tmp_path: Path) -> None:
    """SQL-скрипти створюють і заповнюють ланцюжок; view та SQL-функції дають правильні підсумки."""
    with sqlite3.connect(tmp_path / "seed.sqlite3") as connection:
        connection.executescript(files("result_store").joinpath("schema.sql").read_text())
        connection.executescript(files("result_store").joinpath("seed.sql").read_text())
        rows = connection.execute(
            "SELECT r.run_id,f.source_id,p.channel_index,p.frequency_hz FROM analysis_run r "
            "JOIN file_result f USING(run_id) JOIN spectral_peak p USING(result_id) ORDER BY p.channel_index"
        ).fetchall()
        assert rows == [("seed-run", "tone", 0, 440), ("seed-run", "tone", 1, 1_000)]
        assert connection.execute("SELECT completed_count,success_count,failure_count,duration_seconds FROM run_summary").fetchone() == (2, 1, 1, 1.0)
        assert connection.execute("SELECT round(CAST(frame_count AS REAL)/sample_rate_hz,3) FROM file_result WHERE result_id=1").fetchone()[0] == 1.0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fields_unique_identity_and_error_metadata_are_enforced(tmp_path: Path) -> None:
    """Обов'язкові поля, унікальний ID у запуску та відсутність вигаданих метаданих помилки контролюються БД."""
    with ResultStore(tmp_path / "history.sqlite3") as store:
        run_id = store.create_run(expected_count=3)
        missing = process_file(FileJob("missing", tmp_path / "missing.wav"))
        store.save_result(run_id, missing)
        row = store.list_results(run_id)[0]
        assert row["sample_rate_hz"] is row["channel_count"] is row["frame_count"] is None
        assert row["artifact_name"] is None and row["peaks"] == []
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            store.save_result(run_id, missing)
        for source_id, elapsed, rate in [(None, 0.1, None), ("negative", -1, None), ("invented", 0.1, 8_000)]:
            with pytest.raises(sqlite3.IntegrityError):
                store.connection.execute(
                    "INSERT INTO file_result (run_id,source_id,source_path,status,worker_pid,elapsed_seconds,"
                    "sample_rate_hz,error_stage,error_code,error_message) VALUES (?,?,?,'failed',1,?,?,'read','bad','bad')",
                    (run_id, source_id, "bad.wav", elapsed, rate),
                )


def test_foreign_keys_and_two_level_cascade(tmp_path: Path) -> None:
    """Зовнішні ключі відхиляють сирітські піки; видалення запуску каскадно прибирає обидва рівні деталей."""
    with ResultStore(tmp_path / "history.sqlite3") as store:
        run_id = store.create_run(expected_count=1)
        store.save_result(run_id, outcome(tmp_path))
        assert store.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            store.connection.execute("INSERT INTO spectral_peak (result_id,channel_index,peak_index,frequency_hz,amplitude) VALUES (999,0,0,440,1)")
        store.connection.execute("DELETE FROM analysis_run WHERE run_id=?", (run_id,))
        assert store.connection.execute("SELECT count(*) FROM file_result").fetchone()[0] == 0
        assert store.connection.execute("SELECT count(*) FROM spectral_peak").fetchone()[0] == 0


def test_triggers_validate_peaks_and_freeze_saved_results(tmp_path: Path) -> None:
    """Тригери перевіряють канал і Найквіст; збережені метадані й піки не можна переписати."""
    with ResultStore(tmp_path / "history.sqlite3") as store:
        run_id = store.create_run(expected_count=2)
        result_id = store.save_result(run_id, outcome(tmp_path))
        for channel, frequency, amplitude in [(2, 440, 1), (0, 4_001, 1), (0, 0, 1), (0, 440, float("inf"))]:
            with pytest.raises(sqlite3.IntegrityError):
                store.connection.execute(
                    "INSERT INTO spectral_peak (result_id,channel_index,peak_index,frequency_hz,amplitude) VALUES (?,?,99,?,?)",
                    (result_id, channel, frequency, amplitude),
                )
        assert store.list_results(run_id)[0]["peaks"][0]["amplitude"] > 1
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store.connection.execute("UPDATE file_result SET sample_rate_hz=1 WHERE result_id=?", (result_id,))
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store.connection.execute("UPDATE spectral_peak SET amplitude=0.5 WHERE result_id=?", (result_id,))
        failed_id = store.save_result(run_id, process_file(FileJob("bad", tmp_path / "absent.wav")))
        with pytest.raises(sqlite3.IntegrityError, match="successful"):
            store.connection.execute("INSERT INTO spectral_peak (result_id,channel_index,peak_index,frequency_hz,amplitude) VALUES (?,0,0,440,1)", (failed_id,))


def test_run_finishes_only_after_all_results_and_rejects_late_writes(tmp_path: Path) -> None:
    """Завершення вимагає всі результати; завершений запуск не приймає нових даних і повторного завершення."""
    with ResultStore(tmp_path / "history.sqlite3") as store:
        run_id = store.create_run(expected_count=2)
        good = outcome(tmp_path)
        store.save_result(run_id, good)
        with pytest.raises(sqlite3.IntegrityError, match="not all"):
            store.finish_run(run_id)
        assert store.get_run(run_id)["status"] == "running"
        store.save_result(run_id, process_file(FileJob("bad", tmp_path / "absent.wav")))
        store.finish_run(run_id)
        assert store.get_run(run_id)["status"] == "completed"
        with pytest.raises(sqlite3.IntegrityError, match="not running"):
            store.save_result(run_id, good)
        with pytest.raises(sqlite3.IntegrityError, match="once"):
            store.finish_run(run_id)


def test_failed_peak_insert_rolls_back_parent_and_removes_artifact(tmp_path: Path) -> None:
    """Помилка піка відкочує весь результат файла й прибирає створений NPZ; повторна коректна спроба можлива."""
    with ResultStore(tmp_path / "history.sqlite3") as store:
        run_id = store.create_run(expected_count=1)
        good = outcome(tmp_path)
        invalid_packet = replace(
            good.packet,
            peaks_by_channel=((SpectralPeak(0, 440, 1.0), SpectralPeak(0, 5_000, 1.0)), ()),
        )
        invalid = replace(good, packet=invalid_packet)
        with pytest.raises(sqlite3.IntegrityError, match="Nyquist"):
            store.save_result(run_id, invalid)
        assert store.list_results(run_id) == []
        assert store.connection.execute("SELECT count(*) FROM spectral_peak").fetchone()[0] == 0
        assert list(store.artifact_dir.iterdir()) == []
        store.save_result(run_id, good)
        assert len(store.list_results(run_id)) == 1
        assert len(list(store.artifact_dir.glob("*.npz"))) == 1


def test_reopen_restores_full_arrays_configs_identity_and_peaks(tmp_path: Path) -> None:
    """Після закриття БД відновлюються всі масиви, конфігурації, ідентичність і піки реального DSP-результату."""
    path = tmp_path / "history.sqlite3"
    original = outcome(tmp_path)
    with ResultStore(path) as store:
        run_id = store.create_run(expected_count=1)
        with pytest.raises(ValueError, match="schema_version"):
            store.save_result(run_id, replace(original, packet=replace(original.packet, schema_version=2)))
        result_id = store.save_result(run_id, original)
        store.finish_run(run_id)
    original.job.path.unlink()
    with ResultStore(path) as reopened:
        restored = reopened.load_result(result_id)
        assert restored.job == original.job
        assert restored.worker_pid == original.worker_pid
        assert restored.packet.filter_config == original.packet.filter_config
        assert restored.packet.peak_config == original.packet.peak_config
        assert restored.packet.peaks_by_channel == original.packet.peaks_by_channel
        np.testing.assert_array_equal(restored.packet.samples, original.packet.samples)
        np.testing.assert_array_equal(restored.packet.spectrum.frequencies_hz, original.packet.spectrum.frequencies_hz)
        np.testing.assert_array_equal(restored.packet.spectrum.amplitudes, original.packet.spectrum.amplitudes)
        assert reopened.list_runs()[0]["run_id"] == run_id


def test_same_source_in_another_run_and_failed_run_history(tmp_path: Path) -> None:
    """Один source_id дозволений у різних запусках; незавершений через інфраструктуру запуск зберігає причину."""
    with ResultStore(tmp_path / "history.sqlite3") as store:
        missing = process_file(FileJob("same", tmp_path / "absent.wav"))
        first = store.create_run(expected_count=1)
        error_id = store.save_result(first, missing)
        store.finish_run(first)
        second = store.create_run(expected_count=2)
        store.save_result(second, missing)
        store.finish_run(second, error_message="controlled storage interruption")
        assert store.load_result(error_id).error == missing.error
        assert store.get_run(second)["status"] == "failed"
        assert store.get_run(second)["completed_count"] == 1
        assert store.list_runs()[0]["run_id"] == second


def test_every_connection_enforces_foreign_keys_and_unknown_schema_is_rejected(tmp_path: Path) -> None:
    """Повторне відкриття вмикає FK; непідтримувана версія схеми відхиляється без переписування."""
    path = tmp_path / "history.sqlite3"
    with ResultStore(path) as store:
        assert store.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with ResultStore(path) as store:
        assert store.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        store.connection.execute("PRAGMA user_version=2")
    with pytest.raises(ValueError, match="schema version"):
        ResultStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
