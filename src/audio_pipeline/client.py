"""Small streaming HTTP client for submitting one WAV to the local service."""

from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import uuid4


_CHUNK_BYTES = 1024 * 1024


def analyze_file(
    path: str | Path,
    *,
    server_url: str = "http://127.0.0.1:8765",
    source_id: str | None = None,
    filter_kind: str | None = None,
    cutoff_hz: float | None = None,
    filter_order: int = 4,
    max_peaks: int = 5,
    min_amplitude_ratio: float = 0.05,
    min_frequency_hz: float = 0.0,
    min_separation_hz: float = 0.0,
    timeout_seconds: float = 60.0,
) -> tuple[int, dict[str, Any]]:
    """Stream a WAV file to ``POST /analyze`` and return status plus JSON body."""

    audio_path = Path(path)
    if not audio_path.is_file():
        raise FileNotFoundError(f"WAV файл не знайдено: {audio_path}")
    parsed_url = urlsplit(server_url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.hostname:
        raise ValueError("server_url має бути HTTP(S) URL з ім’ям хоста.")
    if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
        raise ValueError("server_url не має містити credentials, query чи fragment.")

    connection_type = (
        http.client.HTTPSConnection
        if parsed_url.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connection_type(
        parsed_url.hostname,
        parsed_url.port,
        timeout=timeout_seconds,
    )
    target_path = f"{parsed_url.path.rstrip('/')}/analyze"
    options = {
        "source_id": source_id or uuid4().hex,
        "source_name": audio_path.name,
        "max_peaks": str(max_peaks),
        "min_amplitude_ratio": str(min_amplitude_ratio),
        "min_frequency_hz": str(min_frequency_hz),
        "min_separation_hz": str(min_separation_hz),
    }
    if filter_kind is not None:
        options["filter_kind"] = filter_kind
    if cutoff_hz is not None:
        options["cutoff_hz"] = str(cutoff_hz)
    if filter_kind is not None or cutoff_hz is not None:
        options["filter_order"] = str(filter_order)
    target_path = f"{target_path}?{urlencode(options)}"

    try:
        with audio_path.open("rb") as audio_file:
            connection.putrequest("POST", target_path)
            connection.putheader("Content-Type", "audio/wav")
            connection.putheader(
                "Content-Length", str(os.fstat(audio_file.fileno()).st_size)
            )
            connection.putheader("Accept", "application/json")
            connection.endheaders()
            while chunk := audio_file.read(_CHUNK_BYTES):
                connection.send(chunk)
        response = connection.getresponse()
        response_body = response.read()
        payload = json.loads(response_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Сервер повернув JSON неочікуваного типу.")
        return response.status, payload
    finally:
        connection.close()
