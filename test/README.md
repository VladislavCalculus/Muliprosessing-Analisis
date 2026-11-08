# MLT-4 and MLT-5 tests

This directory contains local tests for the WAV reader (`audio_io`, MLT-4)
and the signal-processing package (`signal_proc`, MLT-5). Reader tests create
real temporary WAV files. The integration case passes a decoded `AudioPacket`
to the real DSP implementation and checks a 440 Hz tone and its amplitude.

The suite contains **43 collected pytest cases**: 31 reader cases, 2 command-line
cases, and the existing 10 DSP cases. The all-space-filename regression is
POSIX-specific and is skipped on Windows, where that filename is not supported.

## Install and run

From the repository root, activate the project virtual environment, then run:

```sh
source .venv/bin/activate
python -m pip install -e '.[test]'
python test/run_tests.py
```

The suite uses generated signals and disposable local files. It does not
access Jira, network services, microphones, or user audio files.

## WAV-reader coverage

`test_audio_io.py` checks mono/stereo metadata and exact samples; PCM8/16/24/32;
float32/64 and scale preservation; silence and one frame; empty data and
zero-byte files; malformed/truncated headers and data; unsupported containers
and encoding; auxiliary chunks; missing paths and directories; same basenames
with different IDs; empty selection; invalid/duplicate IDs; NaN/Inf; and batch
continuation after a damaged middle file. WAV bit depth is checked against the
header, including PCM24 decoded as int32. Original files must remain unchanged.

`test_audio_io_cli.py` checks visible metadata, result order, batch counters,
and process status after both successful and mixed-result input.

## Test doubles and assertion styles

`test_signal_proc.py` contains a small Butterworth-construction stub and a
`unittest.mock.Mock` for the SOS filter call. Together they verify the boundary
between configuration, filter construction, and returned samples without
replacing the real DSP tests. The suite also uses ordinary `assert`,
`pytest.approx`, `pytest.raises`, NumPy array assertions, and Mock call
assertions.

## Coverage

Coverage.py measures statements and branches in `audio_io` and `signal_proc`:

```sh
python -m coverage run -m pytest test
python -m coverage report -m
```

For an annotated HTML report, run `python3 -m coverage html` and open
`htmlcov/index.html`. Coverage is evidence of executed code paths, not proof of
correctness by itself; review any missing lines against the test scope.

Result recorded on **2026-11-08** using Python 3.12.14, NumPy 2.3.5,
SciPy 1.17.0, pytest 9.2.0, and coverage 7.17.2 on Linux:

- Command: `.venv/bin/python -m coverage run -m pytest test`.
- **43 passed in 2.50 s**.
- Combined statement/branch coverage: **95%** across `audio_io` and `signal_proc`.
- `audio_io/reader.py`: 92%; `audio_io/__main__.py`: 94%; `signal_proc/processing.py`: 97%.
- `audio_contracts` internals are exercised by integration but are not included
  in this coverage measurement. No claim is made about GUI or worker-pool tests.

The command `.venv/bin/python examples/wav_demo.py` also ran successfully:
mono loaded, the damaged middle file returned `invalid_wav`, stereo loaded,
and the zero-byte file returned `empty_audio`; summary: 2 loaded, 2 errors.
This demo deliberately includes invalid files, so those reported errors are
the expected behavior.
