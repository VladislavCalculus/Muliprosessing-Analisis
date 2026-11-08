"""Run the local audio pipeline server or submit a WAV from another terminal."""

from __future__ import annotations

import argparse
from http.client import HTTPException
import json
from pathlib import Path
import sys
from typing import Sequence

from .client import analyze_file
from .server import DEFAULT_MAX_UPLOAD_BYTES, make_server


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("значення має бути додатним")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Локальний потік WAV → AudioPacket → signal_proc через HTTP loopback."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="запустити локальний HTTP-сервер")
    serve.add_argument("--port", type=int, default=8765, help="TCP порт (default: 8765)")
    serve.add_argument(
        "--max-upload-mb",
        type=_positive_int,
        default=DEFAULT_MAX_UPLOAD_BYTES // (1024 * 1024),
        help="ліміт розміру одного WAV у MiB (default: 100)",
    )

    analyze = commands.add_parser("analyze", help="передати WAV серверу й показати результат")
    analyze.add_argument("wav", type=Path, help="локальний WAV-файл")
    analyze.add_argument(
        "--server-url",
        default="http://127.0.0.1:8765",
        help="адреса сервісу або локального тунелю",
    )
    analyze.add_argument("--source-id", help="ідентифікатор для кореляції запиту та результату")
    analyze.add_argument("--filter", dest="filter_kind", choices=("lowpass", "highpass"))
    analyze.add_argument("--cutoff-hz", type=float)
    analyze.add_argument("--filter-order", type=_positive_int, default=4)
    analyze.add_argument("--max-peaks", type=_positive_int, default=5)
    analyze.add_argument("--min-amplitude-ratio", type=float, default=0.05)
    analyze.add_argument("--min-frequency-hz", type=float, default=0.0)
    analyze.add_argument("--min-separation-hz", type=float, default=0.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        if args.port < 1 or args.port > 65535:
            parser.error("--port має бути в діапазоні 1..65535")
        server = make_server(
            port=args.port,
            max_upload_bytes=args.max_upload_mb * 1024 * 1024,
        )
        print(
            f"MLT audio pipeline слухає http://127.0.0.1:{server.server_port} "
            f"(ліміт {server.max_upload_bytes // (1024 * 1024)} MiB); "
            "Ctrl+C для зупинки.",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Зупиняю локальний сервер.", file=sys.stderr)
        finally:
            server.server_close()
        return 0

    if args.filter_kind is None and args.cutoff_hz is not None:
        parser.error("--cutoff-hz потребує --filter")
    if args.filter_kind is not None and args.cutoff_hz is None:
        parser.error("--filter потребує --cutoff-hz")
    try:
        status, payload = analyze_file(
            args.wav,
            server_url=args.server_url,
            source_id=args.source_id,
            filter_kind=args.filter_kind,
            cutoff_hz=args.cutoff_hz,
            filter_order=args.filter_order,
            max_peaks=args.max_peaks,
            min_amplitude_ratio=args.min_amplitude_ratio,
            min_frequency_hz=args.min_frequency_hz,
            min_separation_hz=args.min_separation_hz,
        )
    except (OSError, ValueError, HTTPException, json.JSONDecodeError) as exc:
        print(f"Не вдалося виконати локальний запит: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if status == 200 and payload.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
