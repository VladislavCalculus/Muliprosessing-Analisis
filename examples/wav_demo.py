"""Create disposable WAV examples and demonstrate continuing after a bad file."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import wave

import numpy as np

from audio_io.__main__ import main as show_files


def write_pcm16(path: Path, sample_rate: int, samples: np.ndarray) -> None:
    channels = 1 if samples.ndim == 1 else samples.shape[1]
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples.astype("<i2").tobytes())


def main() -> None:
    with TemporaryDirectory(prefix="mlt4-demo-") as directory:
        folder = Path(directory)
        mono = folder / "mono.wav"
        stereo = folder / "stereo.wav"
        broken = folder / "broken.wav"
        empty = folder / "empty.wav"

        mono_time = np.arange(8_000) / 8_000
        stereo_time = np.arange(32_000) / 16_000
        write_pcm16(mono, 8_000, 10_000 * np.sin(2 * np.pi * 440 * mono_time))
        write_pcm16(
            stereo,
            16_000,
            np.column_stack(
                (
                    10_000 * np.sin(2 * np.pi * 440 * stereo_time),
                    8_000 * np.sin(2 * np.pi * 1_000 * stereo_time),
                )
            ),
        )
        broken.write_bytes(b"This is text, not WAV audio.\n")
        empty.write_bytes(b"")

        print("Демонстрація: правильний файл, пошкоджений, правильний стерео, порожній.")
        show_files([str(mono), str(broken), str(stereo), str(empty)])
        print("Пошкоджений і порожній файли додані навмисно для показу обробки помилок.")


if __name__ == "__main__":
    main()
