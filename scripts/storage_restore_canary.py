#!/usr/bin/env python3
"""Exercise private object upload, signed download, delete, and restore safely.

The script creates only unique ``operations-canary/`` keys and removes them in a
``finally`` block. It never lists, reads, changes, or deletes customer objects.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import urllib.request
import uuid
import wave
import xml.etree.ElementTree as ET

from drumscribe_api.config import Settings
from drumscribe_api.services.storage import ObjectNotFoundError, S3PrivateStorage


def audio_payload() -> bytes:
    target = io.BytesIO()
    with wave.open(target, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\x00\x00" * 8_000)
    return target.getvalue()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def signed_download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"signed download returned HTTP {response.status}")
        return response.read()


async def assert_missing(storage: S3PrivateStorage, key: str) -> None:
    try:
        await storage.head(key)
    except ObjectNotFoundError:
        return
    raise RuntimeError(f"canary cleanup failed for {key}")


async def run(prefix: str) -> dict[str, object]:
    settings = Settings()
    if settings.storage_backend != "s3":
        raise RuntimeError(
            "the restore canary requires the configured private S3 backend"
        )
    storage = S3PrivateStorage(settings)
    run_id = uuid.uuid4().hex
    audio_key = f"{prefix}/{run_id}/playback-canary.wav"
    export_key = f"{prefix}/{run_id}/export-canary.musicxml"
    keys = [audio_key, export_key]
    audio = audio_payload()
    export = b'<?xml version="1.0"?><score-partwise version="4.0"></score-partwise>'

    try:
        await storage.healthcheck()
        await storage.put_bytes(audio_key, audio, "audio/wav")
        audio_meta = await storage.head(audio_key)
        audio_url = await storage.presign_get(audio_key, expires_in=120)
        downloaded_audio = await asyncio.to_thread(signed_download, audio_url.url)
        if sha256(downloaded_audio) != sha256(audio):
            raise RuntimeError("signed audio download hash mismatch")
        with wave.open(io.BytesIO(downloaded_audio), "rb") as source:
            if source.getnchannels() != 1 or source.getframerate() != 8_000:
                raise RuntimeError("restored playback canary is not the expected WAV")

        await storage.put_bytes(
            export_key, export, "application/vnd.recordare.musicxml+xml"
        )
        export_url = await storage.presign_get(export_key, expires_in=120)
        downloaded_export = await asyncio.to_thread(signed_download, export_url.url)
        if sha256(downloaded_export) != sha256(export):
            raise RuntimeError("signed export download hash mismatch")
        ET.fromstring(downloaded_export)

        await storage.delete_many(keys)
        for key in keys:
            await assert_missing(storage, key)

        # Restore from the retained backup bytes and verify the exact object again.
        await storage.put_bytes(audio_key, audio, "audio/wav")
        restored = await storage.read_prefix(audio_key, length=len(audio) + 1)
        if sha256(restored) != sha256(audio):
            raise RuntimeError("restored private object hash mismatch")
        await storage.delete_many([audio_key])
        await assert_missing(storage, audio_key)

        return {
            "status": "pass",
            "scope": prefix,
            "customerObjectsAccessed": 0,
            "audioBytes": len(audio),
            "audioSha256": sha256(audio),
            "audioContentType": audio_meta.content_type,
            "signedPlayback": "pass",
            "signedExport": "pass",
            "delete": "pass",
            "restore": "pass",
            "finalCleanup": "pass",
        }
    finally:
        await storage.delete_many(keys)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="operations-canary")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.prefix)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
