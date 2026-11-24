PRAGMA foreign_keys = ON;
BEGIN;

CREATE TABLE IF NOT EXISTS analysis_run (
    run_id TEXT PRIMARY KEY CHECK (length(trim(run_id)) > 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    expected_count INTEGER NOT NULL CHECK (expected_count >= 0),
    worker_count INTEGER NOT NULL CHECK (worker_count > 0),
    parent_pid INTEGER NOT NULL CHECK (parent_pid > 0),
    filter_json TEXT CHECK (filter_json IS NULL OR json_valid(filter_json)),
    peak_json TEXT NOT NULL CHECK (json_valid(peak_json)),
    error_message TEXT,
    CHECK (
        (status = 'running' AND finished_at IS NULL AND error_message IS NULL)
        OR (status = 'completed' AND finished_at IS NOT NULL AND error_message IS NULL)
        OR (status = 'failed' AND finished_at IS NOT NULL
            AND error_message IS NOT NULL AND length(trim(error_message)) > 0)
    )
) STRICT;

CREATE TABLE IF NOT EXISTS file_result (
    result_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES analysis_run(run_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL CHECK (length(trim(source_id)) > 0),
    source_path TEXT NOT NULL CHECK (length(trim(source_path)) > 0),
    job_name TEXT CHECK (job_name IS NULL OR length(trim(job_name)) > 0),
    source_name TEXT CHECK (source_name IS NULL OR length(trim(source_name)) > 0),
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed')),
    worker_pid INTEGER NOT NULL CHECK (worker_pid > 0),
    elapsed_seconds REAL NOT NULL CHECK (elapsed_seconds BETWEEN 0 AND 1.7976931348623157e308),
    sample_rate_hz INTEGER,
    frame_count INTEGER,
    channel_count INTEGER,
    artifact_name TEXT,
    error_stage TEXT CHECK (error_stage IN ('read', 'process', 'worker')),
    error_code TEXT,
    error_message TEXT,
    UNIQUE (run_id, source_id),
    CHECK (
        (status = 'succeeded'
            AND sample_rate_hz IS NOT NULL AND sample_rate_hz > 0
            AND frame_count IS NOT NULL AND frame_count > 0
            AND channel_count IS NOT NULL AND channel_count > 0
            AND artifact_name IS NOT NULL AND length(trim(artifact_name)) > 0
            AND error_stage IS NULL AND error_code IS NULL AND error_message IS NULL)
        OR (status = 'failed'
            AND sample_rate_hz IS NULL AND frame_count IS NULL AND channel_count IS NULL
            AND artifact_name IS NULL
            AND error_stage IS NOT NULL AND error_code IS NOT NULL
            AND length(trim(error_code)) > 0
            AND error_message IS NOT NULL AND length(trim(error_message)) > 0)
    )
) STRICT;

CREATE TABLE IF NOT EXISTS spectral_peak (
    peak_id INTEGER PRIMARY KEY,
    result_id INTEGER NOT NULL REFERENCES file_result(result_id) ON DELETE CASCADE,
    channel_index INTEGER NOT NULL CHECK (channel_index >= 0),
    peak_index INTEGER NOT NULL CHECK (peak_index >= 0),
    frequency_hz REAL NOT NULL CHECK (frequency_hz > 0 AND frequency_hz <= 1.7976931348623157e308),
    amplitude REAL NOT NULL CHECK (amplitude > 0 AND amplitude <= 1.7976931348623157e308),
    UNIQUE (result_id, channel_index, peak_index)
) STRICT;

CREATE TRIGGER IF NOT EXISTS file_result_run_guard
BEFORE INSERT ON file_result
BEGIN
    SELECT CASE WHEN (SELECT status FROM analysis_run WHERE run_id = NEW.run_id) <> 'running'
        THEN RAISE(ABORT, 'run is not running') END;
    SELECT CASE WHEN (SELECT count(*) FROM file_result WHERE run_id = NEW.run_id)
        >= (SELECT expected_count FROM analysis_run WHERE run_id = NEW.run_id)
        THEN RAISE(ABORT, 'run already has all expected results') END;
END;

CREATE TRIGGER IF NOT EXISTS file_result_immutable
BEFORE UPDATE ON file_result
BEGIN
    SELECT RAISE(ABORT, 'saved file results are immutable');
END;

CREATE TRIGGER IF NOT EXISTS spectral_peak_guard
BEFORE INSERT ON spectral_peak
BEGIN
    SELECT CASE WHEN (SELECT status FROM file_result WHERE result_id = NEW.result_id) <> 'succeeded'
        THEN RAISE(ABORT, 'peaks require a successful file result') END;
    SELECT CASE WHEN NEW.channel_index >=
        (SELECT channel_count FROM file_result WHERE result_id = NEW.result_id)
        THEN RAISE(ABORT, 'peak channel is outside the file channels') END;
    SELECT CASE WHEN NEW.frequency_hz >
        (SELECT sample_rate_hz / 2.0 FROM file_result WHERE result_id = NEW.result_id)
        THEN RAISE(ABORT, 'peak frequency exceeds Nyquist') END;
    SELECT CASE WHEN (SELECT r.status FROM analysis_run r JOIN file_result f USING (run_id)
        WHERE f.result_id = NEW.result_id) <> 'running'
        THEN RAISE(ABORT, 'run is not running') END;
END;

CREATE TRIGGER IF NOT EXISTS spectral_peak_immutable
BEFORE UPDATE ON spectral_peak
BEGIN
    SELECT RAISE(ABORT, 'saved peaks are immutable');
END;

CREATE TRIGGER IF NOT EXISTS analysis_run_finish_guard
BEFORE UPDATE ON analysis_run
BEGIN
    SELECT CASE WHEN OLD.status <> 'running' OR NEW.status = 'running'
        THEN RAISE(ABORT, 'run can only finish once') END;
    SELECT CASE WHEN NEW.run_id IS NOT OLD.run_id OR NEW.created_at IS NOT OLD.created_at
        OR NEW.expected_count IS NOT OLD.expected_count OR NEW.worker_count IS NOT OLD.worker_count
        OR NEW.parent_pid IS NOT OLD.parent_pid OR NEW.filter_json IS NOT OLD.filter_json
        OR NEW.peak_json IS NOT OLD.peak_json
        THEN RAISE(ABORT, 'run parameters are immutable') END;
    SELECT CASE WHEN NEW.status = 'completed' AND NEW.expected_count <>
        (SELECT count(*) FROM file_result WHERE run_id = OLD.run_id)
        THEN RAISE(ABORT, 'not all expected results have been saved') END;
END;

CREATE VIEW IF NOT EXISTS run_summary AS
SELECT r.*,
    count(f.result_id) AS completed_count,
    sum(CASE WHEN f.status = 'succeeded' THEN 1 ELSE 0 END) AS success_count,
    sum(CASE WHEN f.status = 'failed' THEN 1 ELSE 0 END) AS failure_count,
    round((julianday(coalesce(r.finished_at, r.created_at)) - julianday(r.created_at)) * 86400, 3)
        AS duration_seconds
FROM analysis_run r LEFT JOIN file_result f USING (run_id)
GROUP BY r.run_id;

PRAGMA user_version = 1;
COMMIT;
