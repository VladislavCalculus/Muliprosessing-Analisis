"""WAV-reader checks using real temporary files and the public module API."""

from __future__ import annotations

import struct
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from audio_contracts import AudioPacket, AudioReadError
from audio_io import WavFile, WavSource, read_wav, read_wav_batch, read_wav_details
from signal_proc import process_signal


def _chunk(kind: bytes, payload: bytes) -> bytes:
    """Build a RIFF chunk, including its word-alignment byte when needed."""

    return kind + struct.pack("<I", len(payload)) + payload + b"\0" * (len(payload) % 2)


def _riff(*chunks: bytes) -> bytes:
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _fmt(
    *,
    channels: int = 1,
    sample_rate_hz: int = 8_000,
    bits: int = 16,
    format_tag: int = 1,
    block_align: int | None = None,
) -> bytes:
    if block_align is None:
        block_align = channels * (bits // 8)
    return struct.pack(
        "<HHIIHH",
        format_tag,
        channels,
        sample_rate_hz,
        sample_rate_hz * block_align,
        block_align,
        bits,
    )


def _write_pcm(
    path: Path, samples: np.ndarray, sample_rate_hz: int = 8_000, bits: int = 16
) -> Path:
    """Encode PCM independently of the SciPy decoder used by the reader."""

    channels = 1 if samples.ndim == 1 else samples.shape[1]
    if bits == 24:
        data = b"".join(
            int(value).to_bytes(3, "little", signed=True) for value in samples.flat
        )
    else:
        dtype = "u1" if bits == 8 else f"<i{bits // 8}"
        data = samples.astype(dtype).tobytes()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(bits // 8)
        output.setframerate(sample_rate_hz)
        output.writeframes(data)
    return path


def _write_float(path: Path, samples: np.ndarray, sample_rate_hz: int = 8_000) -> Path:
    channels = 1 if samples.ndim == 1 else samples.shape[1]
    data = samples.astype(samples.dtype.newbyteorder("<"), copy=False).tobytes()
    path.write_bytes(
        _riff(
            _chunk(
                b"fmt ",
                _fmt(
                    channels=channels,
                    sample_rate_hz=sample_rate_hz,
                    bits=samples.dtype.itemsize * 8,
                    format_tag=3,
                ),
            ),
            _chunk(b"fact", struct.pack("<I", samples.shape[0])),
            _chunk(b"data", data),
        )
    )
    return path


@pytest.mark.parametrize(
    "sample_rate_hz, channels, frame_count, duration_seconds",
    [(8_000, 1, 8_000, 1.0), (16_000, 2, 32_000, 2.0)],
    ids=["mono-8000Hz-one-second", "stereo-16000Hz-two-seconds"],
)
def test_samples_and_file_parameters_are_preserved(
    tmp_path: Path,
    sample_rate_hz: int,
    channels: int,
    frame_count: int,
    duration_seconds: float,
) -> None:
    samples = np.full(frame_count, 1_000, dtype=np.int16)
    if channels == 2:
        samples = np.column_stack((samples, -samples))
    path = _write_pcm(tmp_path / "recording.wav", samples, sample_rate_hz)
    original_file = path.read_bytes()

    details = read_wav_details(path, source_id="recording-17", source_name="Мій запис")

    assert isinstance(details, WavFile)
    packet = details.packet
    assert isinstance(packet, AudioPacket)
    assert packet.source_id == "recording-17"
    assert packet.source_name == "Мій запис"
    assert packet.sample_rate_hz == sample_rate_hz
    assert packet.channel_count == channels
    assert packet.frame_count == frame_count
    assert packet.duration_seconds == pytest.approx(duration_seconds)
    assert packet.samples.shape == (frame_count, channels)
    assert packet.samples.dtype == np.int16
    assert packet.samples.flags.c_contiguous
    np.testing.assert_array_equal(packet.samples, samples.reshape(frame_count, channels))
    assert details.bits_per_sample == 16
    assert details.encoding == "PCM"
    assert path.read_bytes() == original_file


@pytest.mark.parametrize(
    "bits, values, expected_dtype",
    [
        (8, [0, 1, 128, 254, 255], np.uint8),
        (24, [-8_388_608, -1, 0, 1, 8_388_607], np.int32),
        (32, [-2_147_483_648, -1, 0, 1, 2_147_483_647], np.int32),
    ],
    ids=["unsigned-pcm8", "pcm24-in-int32", "pcm32"],
)
def test_pcm_scale_and_header_bit_depth(
    tmp_path: Path, bits: int, values: list[int], expected_dtype: type
) -> None:
    samples = np.array(values, dtype=np.int64)
    path = _write_pcm(tmp_path / "samples.wav", samples, bits=bits)

    details = read_wav_details(path, source_id="pcm-source")

    assert isinstance(details, WavFile)
    assert details.bits_per_sample == bits
    assert details.encoding == "PCM"
    assert details.packet.samples.dtype == expected_dtype
    # PCM24 occupies the high 24 bits of int32; its file bit depth is still 24.
    expected = samples * 256 if bits == 24 else samples
    np.testing.assert_array_equal(
        details.packet.samples[:, 0], expected.astype(expected_dtype)
    )


@pytest.mark.parametrize("dtype", [np.float32, np.float64], ids=["float32", "float64"])
def test_float_values_keep_their_original_scale(tmp_path: Path, dtype: type) -> None:
    samples = np.array([-1.75, -0.25, 0.0, 1.5], dtype=dtype)
    path = _write_float(tmp_path / "floating.wav", samples)

    details = read_wav_details(path, source_id="float-source")

    assert isinstance(details, WavFile)
    assert details.encoding == "IEEE_FLOAT"
    assert details.bits_per_sample == np.dtype(dtype).itemsize * 8
    assert details.packet.samples.dtype == dtype
    np.testing.assert_array_equal(details.packet.samples[:, 0], samples)


def test_silence_and_one_frame_are_valid_audio(tmp_path: Path) -> None:
    for name, samples in (
        ("silence", np.zeros(32, dtype=np.int16)),
        ("one-frame", np.array([1_234], dtype=np.int16)),
    ):
        path = _write_pcm(tmp_path / f"{name}.wav", samples)

        result = read_wav(path, source_id=name)

        assert isinstance(result, AudioPacket), name
        assert result.frame_count == len(samples)
        assert result.duration_seconds == pytest.approx(len(samples) / 8_000)
        np.testing.assert_array_equal(result.samples[:, 0], samples)


def test_batch_continues_after_a_damaged_middle_file(tmp_path: Path) -> None:
    first_samples = np.array([100, -100, 200, -200], dtype=np.int16)
    last_samples = np.array([[10, -10], [20, -20]], dtype=np.int16)
    first = _write_pcm(tmp_path / "first.wav", first_samples)
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"This text is not a WAV recording.")
    last = _write_pcm(tmp_path / "last.wav", last_samples, 16_000)
    originals = {path: path.read_bytes() for path in (first, broken, last)}
    sources = [
        WavSource(path=first, source_id="file-1"),
        WavSource(path=broken, source_id="file-2", source_name="Пошкоджений файл"),
        WavSource(path=last, source_id="file-3"),
    ]

    stream = read_wav_batch(iter(sources))
    assert iter(stream) is stream
    results = list(stream)

    assert [result.source_id for result in results] == ["file-1", "file-2", "file-3"]
    assert isinstance(results[0], AudioPacket)
    assert isinstance(results[1], AudioReadError)
    assert isinstance(results[2], AudioPacket)
    assert results[0].source_name == "first.wav"
    assert results[1].source_name == "Пошкоджений файл"
    assert results[1].error_code == "invalid_wav"
    assert results[1].message.strip()
    np.testing.assert_array_equal(results[0].samples[:, 0], first_samples)
    np.testing.assert_array_equal(results[2].samples, last_samples)
    for path, original in originals.items():
        assert path.read_bytes() == original


@pytest.mark.parametrize("has_wav_header", [False, True], ids=["zero-bytes", "zero-frames"])
def test_empty_files_have_a_controlled_error(tmp_path: Path, has_wav_header: bool) -> None:
    path = tmp_path / "empty.wav"
    if has_wav_header:
        _write_pcm(path, np.array([], dtype=np.int16))
    else:
        path.write_bytes(b"")

    result = read_wav(path, source_id="empty-source")

    assert isinstance(result, AudioReadError)
    assert result.source_id == "empty-source"
    assert result.source_name == "empty.wav"
    assert result.error_code == "empty_audio"
    assert result.message.strip()


def _damaged_wav_cases() -> dict[str, bytes]:
    fmt_chunk = _chunk(b"fmt ", _fmt())
    data_chunk = _chunk(b"data", b"\x00\x00\x01\x00")
    valid = _riff(fmt_chunk, data_chunk)
    cut = valid[:-2]
    cut_with_matching_riff_size = b"RIFF" + struct.pack("<I", len(cut) - 8) + cut[8:]
    return {
        "text-renamed-wav": b"not an audio file",
        "incomplete-header": b"RIFF\x24\x00",
        "truncated-riff": cut,
        "truncated-data": cut_with_matching_riff_size,
        "zero-channels": _riff(_chunk(b"fmt ", _fmt(channels=0)), data_chunk),
        "zero-sample-rate": _riff(_chunk(b"fmt ", _fmt(sample_rate_hz=0)), data_chunk),
        "bad-block-alignment": _riff(_chunk(b"fmt ", _fmt(block_align=1)), data_chunk),
        "incomplete-frame": _riff(fmt_chunk, _chunk(b"data", b"\x00\x00\x01")),
        "missing-fmt": _riff(data_chunk),
        "missing-data": _riff(fmt_chunk),
        "duplicate-fmt": _riff(fmt_chunk, fmt_chunk, data_chunk),
        "duplicate-data": _riff(fmt_chunk, data_chunk, data_chunk),
    }


_DAMAGED_CASES = _damaged_wav_cases()


@pytest.mark.parametrize("content", _DAMAGED_CASES.values(), ids=_DAMAGED_CASES.keys())
def test_invalid_structure_is_not_reported_as_loaded(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "damaged.wav"
    path.write_bytes(content)

    result = read_wav(path, source_id="damaged-source")

    assert isinstance(result, AudioReadError)
    assert result.error_code == "invalid_wav"
    assert result.source_id == "damaged-source"
    assert result.message.strip()


def test_unsupported_containers_and_encodings_are_reported(tmp_path: Path) -> None:
    # These files identify formats deliberately excluded from the first reader.
    big_endian_body = (
        b"WAVEfmt "
        + struct.pack(">IHHIIHH", 16, 1, 1, 8_000, 16_000, 2, 16)
        + b"data"
        + struct.pack(">I", 2)
        + b"\x00\x00"
    )
    rifx = b"RIFX" + struct.pack(">I", len(big_endian_body)) + big_endian_body
    fmt_chunk = _chunk(b"fmt ", _fmt())
    rf64_data = b"data" + struct.pack("<I", 0xFFFFFFFF) + b"\x00\x00"
    rf64_riff_size = 4 + 8 + 28 + len(fmt_chunk) + len(rf64_data)
    rf64 = (
        b"RF64"
        + struct.pack("<I", 0xFFFFFFFF)
        + b"WAVE"
        + _chunk(b"ds64", struct.pack("<QQQI", rf64_riff_size, 2, 1, 0))
        + fmt_chunk
        + rf64_data
    )
    pcm_subformat_guid = bytes.fromhex("0100000000001000800000aa00389b71")
    extensible_fmt = (
        _fmt(format_tag=0xFFFE)
        + struct.pack("<HHI", 22, 16, 4)
        + pcm_subformat_guid
    )
    cases = {
        "rifx": rifx,
        "rf64": rf64,
        "extensible": _riff(_chunk(b"fmt ", extensible_fmt), _chunk(b"data", b"\0\0")),
        "a-law": _riff(
            _chunk(b"fmt ", _fmt(bits=8, format_tag=6) + b"\0\0"),
            _chunk(b"fact", struct.pack("<I", 2)),
            _chunk(b"data", b"\xd5\xd5"),
        ),
    }
    for name, content in cases.items():
        path = tmp_path / f"{name}.wav"
        path.write_bytes(content)

        result = read_wav(path, source_id=name)

        assert isinstance(result, AudioReadError), name
        assert result.error_code == "unsupported_format", name
        assert result.source_id == name


def test_missing_path_and_directory_return_read_failed(tmp_path: Path) -> None:
    for path in (tmp_path / "missing.wav", tmp_path):
        result = read_wav(path, source_id="unreadable-source")

        assert isinstance(result, AudioReadError)
        assert result.error_code == "read_failed"
        assert result.source_id == "unreadable-source"
        assert result.message.strip()


def test_valid_content_and_unknown_metadata_are_accepted(tmp_path: Path) -> None:
    path = tmp_path / "запис.bin"
    path.write_bytes(
        _riff(
            _chunk(b"xtra", b"abc"),
            _chunk(b"fmt ", _fmt()),
            _chunk(b"data", struct.pack("<hh", -1_000, 1_000)),
            _chunk(b"tail", b"optional metadata"),
        )
    )

    result = read_wav(path, source_id="content-check")

    assert isinstance(result, AudioPacket)
    assert result.source_name == "запис.bin"
    np.testing.assert_array_equal(result.samples[:, 0], [-1_000, 1_000])


def test_equal_filenames_keep_distinct_source_ids(tmp_path: Path) -> None:
    paths = []
    for directory, value in (("left", 100), ("right", -200)):
        folder = tmp_path / directory
        folder.mkdir()
        paths.append(_write_pcm(folder / "same.wav", np.array([value], dtype=np.int16)))

    results = list(
        read_wav_batch(
            [
                WavSource(path=paths[0], source_id="left-id"),
                WavSource(path=paths[1], source_id="right-id"),
            ]
        )
    )

    assert all(isinstance(result, AudioPacket) for result in results)
    assert [result.source_id for result in results] == ["left-id", "right-id"]
    assert [result.source_name for result in results] == ["same.wav", "same.wav"]
    assert results[0].samples[0, 0] == 100
    assert results[1].samples[0, 0] == -200


def test_empty_selection_and_invalid_source_ids(tmp_path: Path) -> None:
    assert list(read_wav_batch([])) == []
    path = _write_pcm(tmp_path / "valid.wav", np.array([0, 1], dtype=np.int16))
    for invalid_id in ("", "   "):
        with pytest.raises(ValueError):
            read_wav(path, source_id=invalid_id)
        with pytest.raises(ValueError):
            list(read_wav_batch([WavSource(path=path, source_id=invalid_id)]))
    with pytest.raises(ValueError):
        list(
            read_wav_batch(
                [
                    WavSource(path=path, source_id="duplicate"),
                    WavSource(path=path, source_id="duplicate"),
                ]
            )
        )


def test_nonfinite_float_samples_have_a_controlled_error(tmp_path: Path) -> None:
    for name, value in (("nan", np.nan), ("infinity", np.inf)):
        path = _write_float(
            tmp_path / f"{name}.wav", np.array([0.0, value], dtype=np.float32)
        )

        result = read_wav(path, source_id=name)

        assert isinstance(result, AudioReadError)
        assert result.error_code == "invalid_wav"
        assert result.source_id == name


def test_decoded_packet_integrates_with_real_signal_processing(tmp_path: Path) -> None:
    time_s = np.arange(8_000, dtype=np.float64) / 8_000
    samples = np.rint(16_384 * np.sin(2 * np.pi * 440 * time_s)).astype(np.int16)
    path = _write_pcm(tmp_path / "tone440.wav", samples)
    original_file = path.read_bytes()

    packet = read_wav(path, source_id="tone-440", source_name="Тон 440 Гц")

    assert isinstance(packet, AudioPacket)
    result = process_signal(packet)
    assert result.source_id == "tone-440"
    assert result.source_name == "Тон 440 Гц"
    assert result.peaks_by_channel[0][0].frequency_hz == pytest.approx(440.0, abs=1.0)
    assert result.peaks_by_channel[0][0].amplitude == pytest.approx(0.5, abs=0.002)
    np.testing.assert_array_equal(packet.samples[:, 0], samples)
    assert path.read_bytes() == original_file


@pytest.mark.skipif(sys.platform == "win32", reason="Windows rejects all-space filenames")
def test_blank_display_filename_does_not_interrupt_batch(tmp_path: Path) -> None:
    blank_name = _write_pcm(tmp_path / "   ", np.array([1, 2, 3], dtype=np.int16))
    next_file = _write_pcm(tmp_path / "next.wav", np.array([4, 5], dtype=np.int16))

    results = list(
        read_wav_batch([WavSource(blank_name, "blank-name"), WavSource(next_file, "next")])
    )

    assert all(isinstance(result, AudioPacket) for result in results)
    assert results[0].source_name is None
    assert [result.source_id for result in results] == ["blank-name", "next"]
