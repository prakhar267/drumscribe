"""Safe audio inspection, normalization, and compact waveform extraction."""

from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_CODECS = frozenset(
    {
        "aac",
        "flac",
        "mp3",
        "pcm_f32be",
        "pcm_f32le",
        "pcm_f64be",
        "pcm_f64le",
        "pcm_s16be",
        "pcm_s16le",
        "pcm_s24be",
        "pcm_s24le",
        "pcm_s32be",
        "pcm_s32le",
        "pcm_s8",
        "pcm_u8",
    }
)
SUPPORTED_FORMAT_TOKENS = frozenset({"aac", "flac", "mp3", "mov", "mp4", "m4a", "wav"})
SUPPORTED_DECLARED_MIME_TYPES = frozenset(
    {
        "audio/aac",
        "audio/flac",
        "audio/m4a",
        "audio/mp4",
        "audio/mpeg",
        "audio/wav",
        "audio/x-flac",
        "audio/x-m4a",
        "audio/x-wav",
    }
)
MIME_FORMAT_TOKENS = {
    "audio/aac": frozenset({"aac"}),
    "audio/flac": frozenset({"flac"}),
    "audio/x-flac": frozenset({"flac"}),
    "audio/mpeg": frozenset({"mp3"}),
    "audio/wav": frozenset({"wav"}),
    "audio/x-wav": frozenset({"wav"}),
    "audio/m4a": frozenset({"m4a", "mov", "mp4"}),
    "audio/x-m4a": frozenset({"m4a", "mov", "mp4"}),
    "audio/mp4": frozenset({"m4a", "mov", "mp4"}),
}


class AudioValidationError(ValueError):
    pass


class AudioToolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    format_name: str
    codec_name: str
    duration_seconds: float
    size_bytes: int
    sample_rate: int
    channels: int
    bit_rate: int | None = None


@dataclass(frozen=True, slots=True)
class WaveformPeaks:
    sample_rate: int
    channels: int
    duration_seconds: float
    peaks: tuple[tuple[float, float], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "sampleRate": self.sample_rate,
            "channels": self.channels,
            "durationSeconds": self.duration_seconds,
            "peaks": [[round(low, 6), round(high, 6)] for low, high in self.peaks],
        }


def _checked_file(path: str | os.PathLike[str]) -> Path:
    candidate = Path(path).expanduser().resolve(strict=True)
    if not candidate.is_file():
        raise AudioValidationError("audio input must be a regular file")
    return candidate


def _resolve_tool(command: str | os.PathLike[str], label: str) -> str:
    value = os.fspath(command)
    resolved = shutil.which(value)
    if resolved is None:
        raise AudioToolError(f"{label} executable was not found: {value!r}")
    return resolved


def probe_audio(
    path: str | os.PathLike[str],
    *,
    ffprobe: str | os.PathLike[str] = "ffprobe",
    timeout_seconds: float = 30,
) -> AudioMetadata:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    source = _checked_file(path)
    executable = _resolve_tool(ffprobe, "ffprobe")
    argv = (
        executable,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "format=format_name,duration,size,bit_rate:stream=codec_name,sample_rate,channels",
        "-of",
        "json",
        os.fspath(source),
    )
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioValidationError("audio inspection timed out") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-500:]
        raise AudioValidationError(f"FFprobe could not read this audio file: {detail}")
    try:
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
        container = payload["format"]
        metadata = AudioMetadata(
            format_name=str(container["format_name"]),
            codec_name=str(stream["codec_name"]),
            duration_seconds=float(container["duration"]),
            size_bytes=source.stat().st_size,
            sample_rate=int(stream["sample_rate"]),
            channels=int(stream["channels"]),
            bit_rate=int(container["bit_rate"]) if container.get("bit_rate") else None,
        )
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AudioValidationError("FFprobe returned incomplete audio metadata") from exc
    if not math.isfinite(metadata.duration_seconds) or metadata.duration_seconds <= 0:
        raise AudioValidationError("audio duration must be positive and finite")
    if metadata.sample_rate < 8_000 or metadata.sample_rate > 384_000:
        raise AudioValidationError("unsupported audio sample rate")
    if metadata.channels < 1 or metadata.channels > 8:
        raise AudioValidationError("unsupported audio channel count")
    return metadata


def validate_audio(
    path: str | os.PathLike[str],
    *,
    declared_mime: str | None = None,
    max_size_bytes: int = 150 * 1024 * 1024,
    max_duration_seconds: float = 12 * 60,
    ffprobe: str | os.PathLike[str] = "ffprobe",
) -> AudioMetadata:
    if max_size_bytes <= 0 or max_duration_seconds <= 0:
        raise ValueError("audio size and duration limits must be positive")
    mime = None
    if declared_mime:
        mime = declared_mime.partition(";")[0].strip().lower()
        if mime not in SUPPORTED_DECLARED_MIME_TYPES:
            raise AudioValidationError(f"unsupported declared MIME type: {mime}")
    metadata = probe_audio(path, ffprobe=ffprobe)
    tokens = set(metadata.format_name.lower().split(","))
    if not tokens.intersection(SUPPORTED_FORMAT_TOKENS):
        raise AudioValidationError(f"unsupported audio container: {metadata.format_name}")
    if metadata.codec_name.lower() not in SUPPORTED_CODECS:
        raise AudioValidationError(f"unsupported audio codec: {metadata.codec_name}")
    if mime and not tokens.intersection(MIME_FORMAT_TOKENS[mime]):
        raise AudioValidationError(
            f"declared MIME type {mime} does not match the detected "
            f"{metadata.format_name} container"
        )
    if metadata.size_bytes > max_size_bytes:
        raise AudioValidationError(f"audio exceeds the configured {max_size_bytes}-byte limit")
    if metadata.duration_seconds > max_duration_seconds:
        raise AudioValidationError(
            f"audio exceeds the configured {max_duration_seconds:g}-second duration limit"
        )
    return metadata


def normalization_argv(
    source: Path,
    destination: Path,
    *,
    ffmpeg: str | os.PathLike[str] = "ffmpeg",
    sample_rate: int = 44_100,
    channels: int = 2,
) -> tuple[str, ...]:
    executable = _resolve_tool(ffmpeg, "ffmpeg")
    if not 8_000 <= sample_rate <= 192_000:
        raise ValueError("sample_rate must be between 8000 and 192000")
    if channels not in (1, 2):
        raise ValueError("channels must be 1 or 2")
    return (
        executable,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        os.fspath(source),
        "-map_metadata",
        "-1",
        "-vn",
        "-sn",
        "-dn",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-f",
        "wav",
        os.fspath(destination),
    )


def normalize_audio(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    ffmpeg: str | os.PathLike[str] = "ffmpeg",
    sample_rate: int = 44_100,
    channels: int = 2,
    timeout_seconds: float = 15 * 60,
    overwrite: bool = False,
) -> Path:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    source_path = _checked_file(source)
    destination_path = Path(destination).expanduser().absolute()
    if source_path == destination_path:
        raise ValueError("normalization destination must differ from source")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists() and not overwrite:
        raise FileExistsError(destination_path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.stem}-", suffix=".wav", dir=destination_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink()  # FFmpeg should create, not overwrite, the temporary file.
    argv = normalization_argv(
        source_path,
        temporary_path,
        ffmpeg=ffmpeg,
        sample_rate=sample_rate,
        channels=channels,
    )
    try:
        completed = subprocess.run(argv, check=False, capture_output=True, timeout=timeout_seconds)
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip()[-1000:]
            raise AudioToolError(f"FFmpeg normalization failed: {detail}")
        if not temporary_path.is_file() or temporary_path.stat().st_size < 44:
            raise AudioToolError("FFmpeg did not produce a valid output file")
        if overwrite:
            os.replace(temporary_path, destination_path)
        else:
            # Hard-link creation is atomic and refuses a destination created concurrently.
            os.link(temporary_path, destination_path)
            temporary_path.unlink()
    except subprocess.TimeoutExpired as exc:
        raise AudioToolError("FFmpeg normalization timed out") from exc
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination_path


def generate_waveform_peaks(
    audio_path: str | os.PathLike[str], *, bins: int = 2_000
) -> WaveformPeaks:
    """Return normalized min/max buckets for an uncompressed PCM WAV."""

    source = _checked_file(audio_path)
    if not 16 <= bins <= 100_000:
        raise ValueError("bins must be between 16 and 100000")
    try:
        with wave.open(os.fspath(source), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            frame_count = handle.getnframes()
            sample_rate = handle.getframerate()
            if frame_count <= 0 or sample_rate <= 0:
                raise AudioValidationError("waveform generation requires non-empty audio")
            if handle.getcomptype() != "NONE" or sample_width not in (1, 2, 3, 4):
                raise AudioValidationError("waveform generation requires integer PCM WAV audio")
            bucket_count = min(bins, max(1, frame_count))
            frames_per_bucket = max(1, math.ceil(frame_count / bucket_count))
            result: list[tuple[float, float]] = []
            maximum = float(2 ** (sample_width * 8 - 1))
            while len(result) < bucket_count:
                raw = handle.readframes(frames_per_bucket)
                if not raw:
                    break
                samples = _decode_pcm(raw, sample_width)
                low = min(samples) / maximum
                high = max(samples) / maximum
                result.append((max(-1.0, low), min(1.0, high)))
    except (wave.Error, EOFError) as exc:
        raise AudioValidationError("waveform generation requires a PCM WAV") from exc
    return WaveformPeaks(sample_rate, channels, frame_count / sample_rate, tuple(result))


def waveform_peaks_json(peaks: WaveformPeaks) -> bytes:
    return json.dumps(peaks.as_dict(), separators=(",", ":"), sort_keys=True).encode("utf-8")


def _decode_pcm(raw: bytes, width: int) -> Sequence[int]:
    if width == 1:
        return [value - 128 for value in raw]
    if width == 2:
        count = len(raw) // 2
        return struct.unpack(f"<{count}h", raw)
    if width == 4:
        count = len(raw) // 4
        return struct.unpack(f"<{count}i", raw)
    return [
        int.from_bytes(raw[index : index + 3], "little", signed=True)
        for index in range(0, len(raw), 3)
    ]
