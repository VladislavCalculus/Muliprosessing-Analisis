"""A small Ukrainian command-line view of the WAV reader."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from audio_contracts import AudioReadError
from .reader import read_wav_details


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Прочитати WAV-файли та показати їхні параметри.")
    parser.add_argument("files", metavar="WAV", nargs="+", type=Path, help="шляхи до WAV-файлів")
    args = parser.parse_args(argv)
    succeeded = 0
    failed = 0

    for index, path in enumerate(args.files, start=1):
        result = read_wav_details(path, source_id=f"file-{index}")
        if isinstance(result, AudioReadError):
            failed += 1
            print(f"[{index}] {result.source_name or '(без назви)'}: помилка ({result.error_code}). {result.message}")
            continue
        succeeded += 1
        packet = result.packet
        print(f"[{index}] {packet.source_name or '(без назви)'}: успішно")
        print(
            f"    Частота дискретизації: {packet.sample_rate_hz} Гц; "
            f"канали: {packet.channel_count}; розрядність: {result.bits_per_sample} біт; "
            f"тривалість: {packet.duration_seconds:g} с."
        )

    print(f"Підсумок: успішно {succeeded}; з помилкою {failed}.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
