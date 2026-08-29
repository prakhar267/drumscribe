import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mutagen

from ..config import Settings
from ..enums import JobErrorCode
from ..errors import APIError

ALLOWED_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mp4",
    "audio/x-m4a",
    "audio/aac",
    "audio/flac",
    "audio/x-flac",
}

ALLOWED_CODECS = {
    "mp3",
    "aac",
    "flac",
    "pcm_s16le",
    "pcm_s24le",
    "pcm_s32le",
    "pcm_f32le",
    "pcm_f64le",
    "alac",
}


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    content_type: str
    codec: str
    duration_seconds: float
    sample_rate: int | None
    channels: int | None
    size_bytes: int


def validate_upload_contract(content_type: str, size_bytes: int, settings: Settings) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized not in ALLOWED_MIME_TYPES:
        raise APIError(
            415,
            JobErrorCode.UNSUPPORTED_CODEC.value,
            "Upload an MP3, WAV, M4A/AAC, or FLAC audio file.",
        )
    if size_bytes > settings.max_upload_bytes:
        raise APIError(
            413,
            JobErrorCode.AUDIO_TOO_LARGE.value,
            f"Audio must be no larger than {settings.max_upload_bytes} bytes.",
        )
    return normalized


def sniff_content_type(prefix: bytes) -> str | None:
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WAVE":
        return "audio/wav"
    if prefix.startswith(b"fLaC"):
        return "audio/flac"
    if prefix.startswith(b"ID3") or (
        len(prefix) >= 2 and prefix[0] == 0xFF and prefix[1] & 0xE0 == 0xE0
    ):
        # MP3 and raw AAC share sync prefixes; ffprobe resolves the codec below.
        return "audio/mpeg"
    if len(prefix) >= 12 and prefix[4:8] == b"ftyp":
        return "audio/mp4"
    return None


def _mime_family(content_type: str) -> str:
    if content_type in {"audio/wav", "audio/x-wav", "audio/wave"}:
        return "wav"
    if content_type in {"audio/flac", "audio/x-flac"}:
        return "flac"
    if content_type in {"audio/mpeg", "audio/mp3"}:
        return "mpeg"
    if content_type in {"audio/mp4", "audio/x-m4a"}:
        return "mp4"
    return "aac"


class AudioProbe:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def inspect(
        self,
        path: Path,
        *,
        declared_content_type: str,
        size_bytes: int,
    ) -> AudioMetadata:
        normalized = validate_upload_contract(declared_content_type, size_bytes, self.settings)
        prefix = await self._prefix(path)
        sniffed = sniff_content_type(prefix)
        if sniffed is None:
            raise APIError(
                422,
                JobErrorCode.INVALID_AUDIO.value,
                "The uploaded file is not valid supported audio.",
            )

        metadata = await self._ffprobe(path)
        if metadata is None:
            metadata = await asyncio.to_thread(self._mutagen_probe, path)
        if metadata is None:
            raise APIError(
                422,
                JobErrorCode.INVALID_AUDIO.value,
                "The uploaded file is malformed or could not be decoded.",
            )
        codec, duration, sample_rate, channels = metadata
        if codec not in ALLOWED_CODECS:
            raise APIError(
                415,
                JobErrorCode.UNSUPPORTED_CODEC.value,
                "The file container is recognized, but its audio codec is unsupported.",
            )
        actual_mime = self._mime_for_codec(codec, sniffed)
        if _mime_family(normalized) != _mime_family(actual_mime):
            # Raw AAC can look like an MPEG sync frame; ffprobe is authoritative for this case.
            if not (normalized == "audio/aac" and codec == "aac"):
                raise APIError(
                    422,
                    JobErrorCode.INVALID_AUDIO.value,
                    "The declared media type does not match the uploaded audio.",
                )
        if duration <= 0:
            raise APIError(422, JobErrorCode.INVALID_AUDIO.value, "Audio duration is invalid.")
        if duration > self.settings.max_audio_duration_seconds:
            raise APIError(
                422,
                JobErrorCode.AUDIO_TOO_LONG.value,
                (
                    "Audio must be no longer than "
                    f"{self.settings.max_audio_duration_seconds:g} seconds."
                ),
            )
        return AudioMetadata(
            content_type=actual_mime,
            codec=codec,
            duration_seconds=duration,
            sample_rate=sample_rate,
            channels=channels,
            size_bytes=size_bytes,
        )

    async def _prefix(self, path: Path) -> bytes:
        def read() -> bytes:
            with path.open("rb") as handle:
                return handle.read(64)

        return await asyncio.to_thread(read)

    async def _ffprobe(
        self, path: Path
    ) -> tuple[str, float, int | None, int | None] | None:
        try:
            process = await asyncio.create_subprocess_exec(
                self.settings.ffprobe_binary,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels,duration:format=duration",
                "-of",
                "json",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return None
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30)
        except TimeoutError:
            process.kill()
            await process.wait()
            return None
        if process.returncode != 0:
            return None
        try:
            payload: dict[str, Any] = json.loads(stdout)
            stream = payload["streams"][0]
            duration = float(stream.get("duration") or payload.get("format", {}).get("duration"))
            return (
                str(stream["codec_name"]),
                duration,
                int(stream["sample_rate"]) if stream.get("sample_rate") else None,
                int(stream["channels"]) if stream.get("channels") else None,
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _mutagen_probe(path: Path) -> tuple[str, float, int | None, int | None] | None:
        try:
            audio = mutagen.File(path)
        except (mutagen.MutagenError, OSError):
            return None
        if audio is None or not getattr(audio, "info", None):
            return None
        info = audio.info
        class_name = audio.__class__.__name__.lower()
        if "wave" in class_name:
            codec = "pcm_s16le"
        elif "flac" in class_name:
            codec = "flac"
        elif "mp3" in class_name:
            codec = "mp3"
        elif "mp4" in class_name:
            codec = "aac"
        elif "aac" in class_name:
            codec = "aac"
        else:
            return None
        return (
            codec,
            float(info.length),
            int(info.sample_rate) if getattr(info, "sample_rate", None) else None,
            int(info.channels) if getattr(info, "channels", None) else None,
        )

    @staticmethod
    def _mime_for_codec(codec: str, sniffed: str) -> str:
        if codec.startswith("pcm_"):
            return "audio/wav"
        if codec == "flac":
            return "audio/flac"
        if codec == "mp3":
            return "audio/mpeg"
        if codec in {"aac", "alac"}:
            return "audio/mp4" if sniffed == "audio/mp4" else "audio/aac"
        return sniffed
