-- Minimal SQL-only metadata fixture; seed-tone.npz is an illustrative artifact reference.
-- Normal ResultStore initialization does not load this fixture.
PRAGMA foreign_keys = ON;
BEGIN;
INSERT INTO analysis_run
    (run_id, created_at, expected_count, worker_count, parent_pid, peak_json)
VALUES
    ('seed-run', '2026-11-24T10:00:00.000Z', 2, 2, 12345,
     '{"max_peaks":5,"min_amplitude_ratio":0.05,"min_frequency_hz":0.0,"min_separation_hz":0.0}');

INSERT INTO file_result
    (result_id, run_id, source_id, source_path, source_name, status,
     worker_pid, elapsed_seconds, sample_rate_hz, frame_count, channel_count, artifact_name)
VALUES
    (1, 'seed-run', 'tone', 'tone.wav', 'tone.wav', 'succeeded',
     12346, 0.1, 8000, 8000, 2, 'seed-tone.npz');

INSERT INTO spectral_peak (result_id, channel_index, peak_index, frequency_hz, amplitude)
VALUES (1, 0, 0, 440, 0.8), (1, 1, 0, 1000, 0.3);

INSERT INTO file_result
    (result_id, run_id, source_id, source_path, source_name, status,
     worker_pid, elapsed_seconds, error_stage, error_code, error_message)
VALUES
    (2, 'seed-run', 'broken', 'broken.wav', 'broken.wav', 'failed',
     12347, 0.01, 'read', 'invalid_wav', 'Invalid WAV header');

UPDATE analysis_run
SET status = 'completed', finished_at = '2026-11-24T10:00:01.000Z'
WHERE run_id = 'seed-run';
COMMIT;
