"""User-visible output and batch exit status of python -m audio_io."""

from pathlib import Path
import struct
import wave

import pytest

from audio_io.__main__ import main


def make_wav(path: Path) -> Path:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(struct.pack("<hhhh", 1, -1, 2, -2))
    return path


def test_cli_shows_metadata_and_success_status(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    path = make_wav(tmp_path / "мій запис.wav")

    status = main([str(path)])
    output = capsys.readouterr().out

    assert status == 0
    assert "мій запис.wav: успішно" in output
    assert "8000 Гц" in output
    assert "канали: 1" in output
    assert "розрядність: 16 біт" in output
    assert "тривалість: 0.0005 с" in output
    assert "Підсумок: успішно 1; з помилкою 0." in output


def test_cli_reports_bad_middle_file_and_still_loads_last(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    first = make_wav(tmp_path / "first.wav")
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"invalid WAV content")
    last = make_wav(tmp_path / "last.wav")

    status = main([str(first), str(broken), str(last)])
    output = capsys.readouterr().out

    assert status == 1
    assert output.index("first.wav: успішно") < output.index("broken.wav: помилка")
    assert output.index("broken.wav: помилка") < output.index("last.wav: успішно")
    assert "invalid_wav" in output
    assert "Підсумок: успішно 2; з помилкою 1." in output
