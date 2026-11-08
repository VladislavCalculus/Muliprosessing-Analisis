"""Loopback HTTP service for the WAV-reader → signal-processing flow."""

from __future__ import annotations

import ipaddress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
import sys

from audio_contracts import AudioReadError
from audio_io import WavFile, read_wav_details
from signal_proc import FilterConfig, PeakConfig, process_signal


DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024


class AudioPipelineHTTPServer(ThreadingHTTPServer):
    """Threaded server with a bounded upload size for each WAV request."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    ) -> None:
        if (
            isinstance(max_upload_bytes, bool)
            or not isinstance(max_upload_bytes, int)
            or max_upload_bytes < 1
        ):
            raise ValueError("max_upload_bytes must be a positive integer")
        host, port = server_address
        if host.lower() == "localhost":
            host = "127.0.0.1"
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("the audio pipeline server must bind to a loopback IP") from exc
        if address.version != 4 or not address.is_loopback:
            raise ValueError("the audio pipeline server must bind to an IPv4 loopback IP")
        self.max_upload_bytes = max_upload_bytes
        super().__init__((host, port), _AudioPipelineHandler)


def make_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> AudioPipelineHTTPServer:
    """Create the local server; call ``serve_forever`` to start accepting requests."""

    return AudioPipelineHTTPServer(
        (host, port), max_upload_bytes=max_upload_bytes
    )


class _AudioPipelineHandler(BaseHTTPRequestHandler):
    server: AudioPipelineHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        # Avoid writing file names and source IDs from the query string to logs.
        status = args[1] if len(args) > 1 else "-"
        print(
            f"{self.client_address[0]} {self.command} "
            f"{urlsplit(self.path).path} {status}",
            file=sys.stderr,
        )

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if urlsplit(self.path).path == "/health":
            self._send_json(200, {"ok": True, "service": "audio_pipeline"})
            return
        self._send_json(404, {"ok": False, "error": {"error_code": "not_found"}})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        parsed_url = urlsplit(self.path)
        if parsed_url.path != "/analyze":
            self._send_json(404, {"ok": False, "error": {"error_code": "not_found"}})
            return

        try:
            source_id, source_name, filter_config, peak_config = self._request_options(
                parse_qs(parsed_url.query, keep_blank_values=True)
            )
        except (TypeError, ValueError) as exc:
            self._send_error_result(
                400,
                source_id="invalid-request",
                source_name=None,
                code="invalid_request",
                message=str(exc),
            )
            return

        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self._send_error_result(
                411,
                source_id=source_id,
                source_name=source_name,
                code="content_length_required",
                message="Для WAV-запиту потрібен заголовок Content-Length.",
            )
            return
        try:
            content_length = int(length_header)
        except ValueError:
            content_length = -1
        if content_length < 0:
            self._send_error_result(
                400,
                source_id=source_id,
                source_name=source_name,
                code="invalid_content_length",
                message="Content-Length має бути невід’ємним цілим числом.",
            )
            return
        if content_length > self.server.max_upload_bytes:
            self._send_error_result(
                413,
                source_id=source_id,
                source_name=source_name,
                code="upload_too_large",
                message="Розмір WAV перевищує ліміт локального сервера.",
            )
            return

        try:
            with TemporaryDirectory(prefix="mlt-audio-upload-") as upload_dir:
                uploaded_path = Path(upload_dir) / "upload.wav"
                with uploaded_path.open("wb") as uploaded_file:
                    remaining = content_length
                    while remaining:
                        chunk = self.rfile.read(min(_CHUNK_BYTES, remaining))
                        if not chunk:
                            self._send_error_result(
                                400,
                                source_id=source_id,
                                source_name=source_name,
                                code="incomplete_upload",
                                message="З’єднання завершилося до передавання всього WAV-файла.",
                            )
                            return
                        uploaded_file.write(chunk)
                        remaining -= len(chunk)
                result = read_wav_details(
                    uploaded_path,
                    source_id=source_id,
                    source_name=source_name,
                )
                if isinstance(result, AudioReadError):
                    self._send_json(422, {"ok": False, "error": result.to_payload()})
                    return
                self._send_success(result, filter_config, peak_config)
        except OSError:
            self._send_error_result(
                500,
                source_id=source_id,
                source_name=source_name,
                code="temporary_file_error",
                message="Локальний сервер не зміг тимчасово зберегти WAV для читання.",
            )

    @staticmethod
    def _single(options: dict[str, list[str]], name: str) -> str | None:
        values = options.get(name, [])
        if len(values) > 1:
            raise ValueError(f"Параметр {name} можна вказати лише один раз.")
        return values[0] if values else None

    @classmethod
    def _request_options(
        cls, options: dict[str, list[str]]
    ) -> tuple[str, str, FilterConfig | None, PeakConfig]:
        source_id = cls._single(options, "source_id") or uuid4().hex
        if not source_id.strip() or len(source_id) > 128:
            raise ValueError("source_id має містити від 1 до 128 символів.")

        source_name = cls._single(options, "source_name") or "upload.wav"
        # Keep a display name, never a client-supplied filesystem path.
        source_name = source_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not source_name or len(source_name) > 255:
            raise ValueError("source_name має містити від 1 до 255 символів.")

        filter_kind = cls._single(options, "filter_kind")
        cutoff_text = cls._single(options, "cutoff_hz")
        if (filter_kind is None) != (cutoff_text is None):
            raise ValueError("filter_kind і cutoff_hz потрібно вказувати разом.")
        filter_config = None
        if filter_kind is not None and cutoff_text is not None:
            filter_config = FilterConfig(
                kind=filter_kind,
                cutoff_hz=float(cutoff_text),
                order=cls._int_option(options, "filter_order", 4),
            )

        peak_config = PeakConfig(
            max_peaks=cls._int_option(options, "max_peaks", 5),
            min_amplitude_ratio=cls._float_option(
                options, "min_amplitude_ratio", 0.05
            ),
            min_frequency_hz=cls._float_option(
                options, "min_frequency_hz", 0.0
            ),
            min_separation_hz=cls._float_option(
                options, "min_separation_hz", 0.0
            ),
        )
        return source_id, source_name, filter_config, peak_config

    @classmethod
    def _int_option(
        cls, options: dict[str, list[str]], name: str, default: int
    ) -> int:
        value = cls._single(options, name)
        return default if value is None else int(value)

    @classmethod
    def _float_option(
        cls, options: dict[str, list[str]], name: str, default: float
    ) -> float:
        value = cls._single(options, name)
        result = default if value is None else float(value)
        if not math.isfinite(result):
            raise ValueError(f"{name} має бути скінченним числом.")
        return result

    def _send_success(
        self,
        details: WavFile,
        filter_config: FilterConfig | None,
        peak_config: PeakConfig,
    ) -> None:
        try:
            processed = process_signal(
                details.packet,
                filter_config=filter_config,
                peak_config=peak_config,
            )
        except ValueError as exc:
            self._send_error_result(
                422,
                source_id=details.packet.source_id,
                source_name=details.packet.source_name,
                code="invalid_processing_config",
                message=str(exc),
            )
            return

        payload: dict[str, Any] = {
            "ok": True,
            "source_id": processed.source_id,
            "source_name": processed.source_name,
            "audio": {
                "sample_rate_hz": processed.sample_rate_hz,
                "frame_count": processed.frame_count,
                "channel_count": processed.channel_count,
                "duration_seconds": processed.duration_seconds,
                "bits_per_sample": details.bits_per_sample,
                "encoding": details.encoding,
            },
            "analysis": {
                "bin_width_hz": processed.spectrum.bin_width_hz,
                "peaks_by_channel": [
                    [
                        {
                            "channel_index": peak.channel_index,
                            "frequency_hz": peak.frequency_hz,
                            "amplitude": peak.amplitude,
                        }
                        for peak in channel
                    ]
                    for channel in processed.peaks_by_channel
                ],
                "filter": (
                    None
                    if filter_config is None
                    else {
                        "kind": filter_config.kind,
                        "cutoff_hz": filter_config.cutoff_hz,
                        "order": filter_config.order,
                    }
                ),
            },
        }
        self._send_json(200, payload)

    def _send_error_result(
        self,
        status: int,
        *,
        source_id: str,
        source_name: str | None,
        code: str,
        message: str,
    ) -> None:
        error = AudioReadError(
            source_id=source_id,
            source_name=source_name,
            error_code=code,
            message=message,
        )
        self._send_json(status, {"ok": False, "error": error.to_payload()})

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(
            payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
