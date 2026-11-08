# MLT-5 unit tests

This directory contains host-only unit tests for the `signal_proc` package. The
selected module accepts `AudioPacket` objects; WAV parsing is not included
because the repository does not yet contain an MLT-4 reader.

The suite contains exactly 10 collected pytest cases covering FFT/peak
behavior, channels, real filters, test doubles, PCM conversion, edge cases,
validation, and payload/pickle behavior.

## Install and run

From the repository root, activate the project virtual environment, then run:

```sh
source .venv/bin/activate
python -m pip install -e '.[test]'
python test/run_tests.py
```

The suite uses synthetic NumPy signals only. It does not access audio files,
Jira, network services, or hardware.

## Test doubles and assertion styles

`test_signal_proc.py` contains a small Butterworth-construction stub and a
`unittest.mock.Mock` for the SOS filter call. Together they verify the boundary
between configuration, filter construction, and returned samples without
replacing the real DSP tests. The suite also uses ordinary `assert`,
`pytest.approx`, `pytest.raises`, NumPy array assertions, and Mock call
assertions.

## Coverage

Coverage.py measures statements and branches in `signal_proc`:

```sh
python -m coverage run --branch --source=signal_proc -m pytest test
python -m coverage report -m
```

For an annotated HTML report, run `python3 -m coverage html` and open
`htmlcov/index.html`. Coverage is evidence of executed code paths, not proof of
correctness by itself; review any missing lines against the test scope.

Latest result: **10 passed; 97% combined statement/branch coverage** for
`signal_proc` (`__init__.py` 100%, `processing.py` 97%). Four statements were
missed and three branches were partial: the zero-gain window fallback, a
frequency floor excluding every bin, and an in-range peak rejected by minimum
separation. WAV parsing and `audio_contracts` internals are outside this
measurement.
