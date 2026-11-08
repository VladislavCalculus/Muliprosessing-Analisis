"""MLT-4: bounded WAV header checks, decoding, and per-file errors.

The first version supports RIFF/WAVE with PCM8/16/24/32 or IEEE float32/64.
Source files are opened read-only. The shared AudioPacket contract is unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from os import PathLike, fstat
from pathlib import Path
import struct
from typing import BinaryIO
import warnings

from scipy.io import wavfile

from audio_contracts import AudioPacket, AudioReadError, AudioReadResult


def _validate_identity(source_id: str, source_name: str | None) -> None:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must be a non-empty string")
    if source_name is not None and (
        not isinstance(source_name, str) or not source_name.strip()
    ):
        raise ValueError("source_name must be None or a non-empty string")


@dataclass(frozen=True, slots=True)
class WavSource:
    """One input selected by the caller; IDs must be unique within a batch."""

    path: str | PathLike[str]
    source_id: str
    source_name: str | None = None

    def __post_init__(self) -> None:
        _validate_identity(self.source_id, self.source_name)
        object.__setattr__(self, "path", Path(self.path))


@dataclass(frozen=True, slots=True)
class WavFile:
    """Decoded audio plus WAV-specific information for presentation.

    Pass packet directly to process_signal. Bit depth comes from the WAV header,
    not the NumPy dtype: 24-bit PCM is decoded into left-aligned int32 values.
    """

    packet: AudioPacket
    bits_per_sample: int
    encoding: str


@dataclass(frozen=True, slots=True)
class _WavHeader:
    sample_rate_hz: int
    channel_count: int
    frame_count: int
    bits_per_sample: int
    encoding: str


class _WavProblem(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _invalid(message: str) -> _WavProblem:
    return _WavProblem("invalid_wav", message)


def _read_header(stream: BinaryIO) -> _WavHeader:
    """Check all chunk boundaries before SciPy can accept a partial recording."""

    file_size = fstat(stream.fileno()).st_size
    if file_size == 0:
        raise _WavProblem("empty_audio", "Файл порожній: у ньому немає аудіоданих.")

    header = stream.read(12)
    if len(header) != 12 or header[8:12] != b"WAVE":
        raise _invalid("Файл не містить правильного заголовка WAV.")
    if header[:4] in (b"RIFX", b"RF64", b"BW64"):
        raise _WavProblem(
            "unsupported_format", "Цей різновид WAV поки не підтримується; потрібен RIFF/WAVE."
        )
    if header[:4] != b"RIFF":
        raise _invalid("Файл не містить правильного заголовка RIFF/WAVE.")
    riff_end = struct.unpack_from("<I", header, 4)[0] + 8
    if riff_end != file_size or riff_end < 12:
        raise _invalid("Розмір WAV не відповідає заголовку: файл неповний або пошкоджений.")

    format_values: tuple[int, int, int, str] | None = None
    frame_count: int | None = None
    block_align = 0

    while stream.tell() < riff_end:
        chunk_header = stream.read(8)
        if len(chunk_header) != 8:
            raise _invalid("У WAV обірваний заголовок блока даних.")
        chunk_id, chunk_size = struct.unpack("<4sI", chunk_header)
        chunk_end = stream.tell() + chunk_size
        if chunk_end > riff_end:
            raise _invalid("У WAV бракує частини даних, зазначених у заголовку.")

        if chunk_id == b"fmt ":
            if format_values is not None or chunk_size < 16:
                raise _invalid("Блок параметрів WAV відсутній, неповний або повторюється.")
            raw_format = stream.read(16)
            if len(raw_format) != 16:
                raise _invalid("Не вдалося повністю прочитати параметри WAV.")
            tag, channels, rate, byte_rate, block_align, bits = struct.unpack(
                "<HHIIHH", raw_format
            )
            if tag not in (1, 3):
                raise _WavProblem(
                    "unsupported_format", "Кодування WAV не підтримується; потрібен PCM або IEEE float."
                )
            supported_bits = (8, 16, 24, 32) if tag == 1 else (32, 64)
            if bits not in supported_bits:
                raise _WavProblem("unsupported_format", "Розрядність цього WAV не підтримується.")
            if channels == 0 or rate == 0:
                raise _invalid("Кількість каналів і частота дискретизації мають бути більші за нуль.")
            if block_align != channels * (bits // 8) or byte_rate != rate * block_align:
                raise _invalid("Параметри каналів, розрядності та розміру кадру WAV не узгоджені.")
            format_values = (rate, channels, bits, "PCM" if tag == 1 else "IEEE_FLOAT")

        elif chunk_id == b"data":
            if format_values is None or frame_count is not None:
                raise _invalid("WAV має містити один блок аудіоданих після блока параметрів.")
            if chunk_size % block_align:
                raise _invalid("Останній звуковий кадр WAV неповний.")
            frame_count = chunk_size // block_align

        # Auxiliary chunks are allowed. Writers such as wave/SciPy can omit
        # the alignment byte on the final odd-sized chunk; accept that case.
        next_chunk = chunk_end + (chunk_size % 2)
        stream.seek(chunk_end if chunk_end == riff_end else next_chunk)

    if format_values is None or frame_count is None:
        raise _invalid("У WAV немає обов'язкового блока параметрів або аудіоданих.")
    if frame_count == 0:
        raise _WavProblem("empty_audio", "WAV містить заголовок, але не містить звукових кадрів.")
    rate, channels, bits, encoding = format_values
    return _WavHeader(rate, channels, frame_count, bits, encoding)


def read_wav_details(
    path: str | PathLike[str],
    *,
    source_id: str,
    source_name: str | None = None,
) -> WavFile | AudioReadError:
    """Decode one file, keeping original samples and WAV bit-depth metadata.

    File failures become AudioReadError. Invalid caller-supplied identity or path
    types are API errors and raise ValueError/TypeError. File extension is not
    used to decide whether the contents are WAV.
    """

    _validate_identity(source_id, source_name)
    wav_path = Path(path)
    default_name = wav_path.name
    if not default_name.strip():
        default_name = None
    name = source_name if source_name is not None else default_name

    def error(code: str, message: str) -> AudioReadError:
        return AudioReadError(source_id, code, message, source_name=name)

    try:
        if not wav_path.is_file():
            return error("read_failed", "Файл не знайдено, недоступний або шлях указує на папку.")
        with wav_path.open("rb") as stream:
            header = _read_header(stream)
            stream.seek(0)
            with warnings.catch_warnings():
                # Unknown, well-bounded metadata chunks are harmless. Header
                # and decoded frame checks reject truncation independently.
                warnings.simplefilter("ignore", wavfile.WavFileWarning)
                sample_rate, samples = wavfile.read(stream, mmap=False)
            packet = AudioPacket(
                source_id=source_id,
                source_name=name,
                sample_rate_hz=sample_rate,
                samples=samples,
            )
            if (
                packet.sample_rate_hz != header.sample_rate_hz
                or packet.channel_count != header.channel_count
                or packet.frame_count != header.frame_count
            ):
                raise _invalid("Прочитані аудіодані не відповідають параметрам WAV.")
            return WavFile(packet, header.bits_per_sample, header.encoding)
    except _WavProblem as exc:
        return error(exc.error_code, str(exc))
    except OSError:
        return error("read_failed", "Не вдалося відкрити або прочитати файл. Перевір шлях і доступ.")
    except (EOFError, ValueError, struct.error):
        return error("invalid_wav", "WAV пошкоджений або містить некоректні аудіодані.")


def read_wav(
    path: str | PathLike[str],
    *,
    source_id: str,
    source_name: str | None = None,
) -> AudioReadResult:
    """Return the existing module contract: AudioPacket or AudioReadError."""

    result = read_wav_details(path, source_id=source_id, source_name=source_name)
    return result.packet if isinstance(result, WavFile) else result


def read_wav_batch(sources: Iterable[WavSource]) -> Iterator[AudioReadResult]:
    """Read in input order, yielding one result at a time, including failures.

    Empty input performs no reads. Duplicate IDs and invalid source descriptors
    are caller errors; file errors are returned and never interrupt later files.
    This function is sequential; process scheduling belongs to MLT-2.
    """

    seen_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, WavSource):
            raise TypeError("sources must contain WavSource objects")
        if source.source_id in seen_ids:
            raise ValueError("source_id must be unique within a batch")
        seen_ids.add(source.source_id)
        yield read_wav(
            source.path, source_id=source.source_id, source_name=source.source_name
        )
