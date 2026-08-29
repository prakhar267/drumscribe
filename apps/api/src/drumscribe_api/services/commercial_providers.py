"""Commercial HTTP provider adapters.

The adapters normalize vendor responses at the boundary and deliberately require
an explicit contract reference. They never fall back to fixture or research output.
"""

from __future__ import annotations

import asyncio
import json
import math
import statistics
import time
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ..enums import Instrument
from .pipeline_contracts import (
    Beat,
    BeatTrackingResult,
    DrumTranscriptionResult,
    ProviderCategory,
    ProviderErrorCategory,
    ProviderRunMetadata,
    RawDrumHit,
    SeparatedAudioResult,
    TempoSegment,
)


class CommercialProviderError(RuntimeError):
    def __init__(
        self,
        category: ProviderErrorCategory,
        message: str,
        *,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.request_id = request_id


@dataclass(frozen=True, slots=True)
class CommercialHTTPConfig:
    api_key: str
    contract_reference: str
    base_url: str
    timeout_seconds: float = 600
    poll_interval_seconds: float = 2

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("commercial provider base URL must use HTTPS")
        if not self.api_key:
            raise ValueError("commercial provider API key is required")
        if not self.contract_reference.strip():
            raise ValueError("commercial provider contract reference is required")
        if self.timeout_seconds <= 0 or self.poll_interval_seconds < 0:
            raise ValueError("provider timeout and polling values are invalid")


def _sanitize_metadata(value: Any) -> Any:
    """Remove secrets and expiring URLs before provider payloads are persisted."""

    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            if any(token in normalized for token in ("key", "secret", "token", "url", "link")):
                continue
            clean[str(key)] = _sanitize_metadata(item)
        return clean
    if isinstance(value, list):
        return [_sanitize_metadata(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _error_category(status_code: int) -> ProviderErrorCategory:
    if status_code in {401, 403}:
        return ProviderErrorCategory.AUTHENTICATION
    if status_code == 429:
        return ProviderErrorCategory.RATE_LIMIT
    if status_code in {400, 404, 409, 413, 415, 422}:
        return ProviderErrorCategory.BAD_INPUT
    return ProviderErrorCategory.UPSTREAM_FAILURE


def _request_id(response: httpx.Response) -> str | None:
    for header in ("x-request-id", "request-id", "x-correlation-id"):
        if value := response.headers.get(header):
            return str(value)
    return None


def _checked_json(response: httpx.Response) -> dict[str, Any]:
    if response.is_error:
        raise CommercialProviderError(
            _error_category(response.status_code),
            f"provider returned HTTP {response.status_code}",
            request_id=_request_id(response),
        )
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CommercialProviderError(
            ProviderErrorCategory.INVALID_RESPONSE,
            "provider returned invalid JSON",
            request_id=_request_id(response),
        ) from exc
    if not isinstance(payload, dict):
        raise CommercialProviderError(
            ProviderErrorCategory.INVALID_RESPONSE,
            "provider JSON must be an object",
            request_id=_request_id(response),
        )
    return payload


async def _download(client: httpx.AsyncClient, url: str, destination: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise CommercialProviderError(
            ProviderErrorCategory.INVALID_RESPONSE,
            "provider output URL must use HTTPS",
        )
    try:
        async with client.stream("GET", url) as response:
            if response.is_error:
                raise CommercialProviderError(
                    ProviderErrorCategory.DOWNLOAD_FAILURE,
                    f"provider output download returned HTTP {response.status_code}",
                    request_id=_request_id(response),
                )
            with destination.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)
    except httpx.TimeoutException as exc:
        raise CommercialProviderError(
            ProviderErrorCategory.TIMEOUT, "provider output download timed out"
        ) from exc
    except httpx.RequestError as exc:
        raise CommercialProviderError(
            ProviderErrorCategory.DOWNLOAD_FAILURE, "provider output download failed"
        ) from exc
    try:
        output_size = (await asyncio.to_thread(destination.stat)).st_size
    except FileNotFoundError:
        output_size = 0
    if output_size == 0:
        raise CommercialProviderError(
            ProviderErrorCategory.INVALID_RESPONSE, "provider returned an empty audio output"
        )


class AudioShakeSourceSeparationProvider:
    provider_id = "audioshake"
    category = ProviderCategory.PRODUCTION_COMMERCIAL

    def __init__(
        self,
        config: CommercialHTTPConfig,
        *,
        model: str = "drums",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.model = model
        self._client = client

    async def separate_drums(
        self, source: Path, destination: Path
    ) -> SeparatedAudioResult:
        started = time.monotonic()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={"x-api-key": self.config.api_key},
            timeout=httpx.Timeout(self.config.timeout_seconds),
        )
        try:
            try:
                with source.open("rb") as handle:
                    upload = await client.post(
                        "/assets",
                        files={"file": (source.name, handle, "audio/wav")},
                    )
                upload_payload = _checked_json(upload)
                asset_id = str(upload_payload.get("id") or "")
                if not asset_id:
                    raise CommercialProviderError(
                        ProviderErrorCategory.INVALID_RESPONSE,
                        "AudioShake upload response omitted asset id",
                    )
                created = await client.post(
                    "/tasks",
                    json={
                        "assetId": asset_id,
                        "metadata": json.dumps({"purpose": "drumscribe-separation"}),
                        "targets": [{"model": self.model, "formats": ["wav"]}],
                    },
                )
                task = _checked_json(created)
                task_id = str(task.get("id") or "")
                if not task_id:
                    raise CommercialProviderError(
                        ProviderErrorCategory.INVALID_RESPONSE,
                        "AudioShake task response omitted task id",
                    )
                task = await self._poll(client, task_id, task)
                target = self._target(task)
                outputs = target.get("output")
                if not isinstance(outputs, list) or not outputs:
                    raise CommercialProviderError(
                        ProviderErrorCategory.INVALID_RESPONSE,
                        "AudioShake drum target omitted its output",
                        request_id=task_id,
                    )
                output = next(
                    (
                        item
                        for item in outputs
                        if isinstance(item, dict) and item.get("format") == "wav"
                    ),
                    outputs[0],
                )
                if not isinstance(output, dict) or not isinstance(output.get("link"), str):
                    raise CommercialProviderError(
                        ProviderErrorCategory.INVALID_RESPONSE,
                        "AudioShake drum output omitted its download link",
                        request_id=task_id,
                    )
                await _download(client, output["link"], destination)
            except httpx.TimeoutException as exc:
                raise CommercialProviderError(
                    ProviderErrorCategory.TIMEOUT, "AudioShake request timed out"
                ) from exc
            except httpx.RequestError as exc:
                raise CommercialProviderError(
                    ProviderErrorCategory.UPSTREAM_FAILURE, "AudioShake request failed"
                ) from exc
            processing_ms = round((time.monotonic() - started) * 1000)
            cost = target.get("cost", task.get("cost"))
            return SeparatedAudioResult(
                drum_audio=destination,
                metadata=ProviderRunMetadata(
                    provider=self.provider_id,
                    category=self.category,
                    model_version=self.model,
                    request_id=task_id,
                    processing_ms=processing_ms,
                    raw_metadata=_sanitize_metadata(task),
                    cost_amount=float(cost) if isinstance(cost, int | float) else None,
                    cost_currency="AudioShake credits" if isinstance(cost, int | float) else None,
                    contract_reference=self.config.contract_reference,
                ),
            )
        finally:
            if owns_client:
                await client.aclose()

    async def _poll(
        self, client: httpx.AsyncClient, task_id: str, initial: dict[str, Any]
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.timeout_seconds
        payload = initial
        while True:
            target = self._target(payload)
            status = str(target.get("status") or "").casefold()
            if status == "completed":
                return payload
            if status == "error":
                raw_error = target.get("error")
                error: dict[str, Any] = raw_error if isinstance(raw_error, dict) else {}
                raise CommercialProviderError(
                    ProviderErrorCategory.UPSTREAM_FAILURE,
                    (
                        "AudioShake target failed: "
                        f"{str(error.get('message') or 'unknown error')[:300]}"
                    ),
                    request_id=task_id,
                )
            if time.monotonic() >= deadline:
                raise CommercialProviderError(
                    ProviderErrorCategory.TIMEOUT,
                    "AudioShake task timed out",
                    request_id=task_id,
                )
            await asyncio.sleep(self.config.poll_interval_seconds)
            payload = _checked_json(await client.get(f"/tasks/{task_id}"))

    def _target(self, task: dict[str, Any]) -> dict[str, Any]:
        targets = task.get("targets")
        if not isinstance(targets, list):
            raise CommercialProviderError(
                ProviderErrorCategory.INVALID_RESPONSE,
                "AudioShake task omitted targets",
                request_id=str(task.get("id") or "") or None,
            )
        target = next(
            (
                item
                for item in targets
                if isinstance(item, dict) and item.get("model") == self.model
            ),
            None,
        )
        if target is None:
            raise CommercialProviderError(
                ProviderErrorCategory.INVALID_RESPONSE,
                "AudioShake task omitted the configured drum target",
                request_id=str(task.get("id") or "") or None,
            )
        return target


class MusicAISourceSeparationProvider:
    provider_id = "music_ai"
    category = ProviderCategory.PRODUCTION_COMMERCIAL

    def __init__(
        self,
        config: CommercialHTTPConfig,
        *,
        workflow: str,
        result_key: str = "drums",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not workflow.strip():
            raise ValueError("Music AI workflow is required")
        self.config = config
        self.workflow = workflow
        self.result_key = result_key
        self._client = client

    async def separate_drums(
        self, source: Path, destination: Path
    ) -> SeparatedAudioResult:
        started = time.monotonic()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={"Authorization": self.config.api_key},
            timeout=httpx.Timeout(self.config.timeout_seconds),
        )
        try:
            try:
                upload = _checked_json(await client.get("/upload"))
                upload_url = upload.get("uploadUrl")
                input_url = upload.get("downloadUrl")
                if not isinstance(upload_url, str) or not isinstance(input_url, str):
                    raise CommercialProviderError(
                        ProviderErrorCategory.INVALID_RESPONSE,
                        "Music AI upload response omitted signed URLs",
                    )
                source_bytes = await asyncio.to_thread(source.read_bytes)
                put_response = await client.put(
                    upload_url,
                    content=source_bytes,
                    headers={"Content-Type": "audio/wav"},
                )
                if put_response.is_error:
                    raise CommercialProviderError(
                        ProviderErrorCategory.UPSTREAM_FAILURE,
                        f"Music AI signed upload returned HTTP {put_response.status_code}",
                    )
                created = _checked_json(
                    await client.post(
                        "/job",
                        json={
                            "name": f"drumscribe-{source.stem[:80]}",
                            "workflow": self.workflow,
                            "params": {"inputUrl": input_url},
                            "metadata": {"purpose": "drumscribe-separation"},
                        },
                    )
                )
                job_id = str(created.get("id") or "")
                if not job_id:
                    raise CommercialProviderError(
                        ProviderErrorCategory.INVALID_RESPONSE,
                        "Music AI job response omitted job id",
                    )
                job = await self._poll(client, job_id)
                results = job.get("result")
                output_url = results.get(self.result_key) if isinstance(results, dict) else None
                if not isinstance(output_url, str):
                    raise CommercialProviderError(
                        ProviderErrorCategory.INVALID_RESPONSE,
                        f"Music AI result omitted configured key {self.result_key!r}",
                        request_id=job_id,
                    )
                await _download(client, output_url, destination)
            except httpx.TimeoutException as exc:
                raise CommercialProviderError(
                    ProviderErrorCategory.TIMEOUT, "Music AI request timed out"
                ) from exc
            except httpx.RequestError as exc:
                raise CommercialProviderError(
                    ProviderErrorCategory.UPSTREAM_FAILURE, "Music AI request failed"
                ) from exc
            return SeparatedAudioResult(
                drum_audio=destination,
                metadata=ProviderRunMetadata(
                    provider=self.provider_id,
                    category=self.category,
                    model_version=self.workflow,
                    request_id=job_id,
                    processing_ms=round((time.monotonic() - started) * 1000),
                    raw_metadata=_sanitize_metadata(job),
                    contract_reference=self.config.contract_reference,
                ),
            )
        finally:
            if owns_client:
                await client.aclose()

    async def _poll(self, client: httpx.AsyncClient, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.timeout_seconds
        while True:
            job = _checked_json(await client.get(f"/job/{job_id}"))
            status = str(job.get("status") or "").upper()
            if status == "SUCCEEDED":
                return job
            if status == "FAILED":
                raw_error = job.get("error")
                error: dict[str, Any] = raw_error if isinstance(raw_error, dict) else {}
                code = str(error.get("code") or "")
                category = (
                    ProviderErrorCategory.BAD_INPUT
                    if code == "BAD_INPUT"
                    else ProviderErrorCategory.TIMEOUT
                    if code == "TIMEOUT"
                    else ProviderErrorCategory.UPSTREAM_FAILURE
                )
                raise CommercialProviderError(
                    category,
                    (
                        "Music AI job failed: "
                        f"{str(error.get('message') or code or 'unknown error')[:300]}"
                    ),
                    request_id=job_id,
                )
            if time.monotonic() >= deadline:
                raise CommercialProviderError(
                    ProviderErrorCategory.TIMEOUT,
                    "Music AI job timed out",
                    request_id=job_id,
                )
            await asyncio.sleep(self.config.poll_interval_seconds)


KLANGIO_INSTRUMENTS: dict[str, Instrument] = {
    "kick": Instrument.KICK,
    "bass_drum": Instrument.KICK,
    "snare": Instrument.SNARE,
    "side_stick": Instrument.CROSS_STICK,
    "cross_stick": Instrument.CROSS_STICK,
    "closed_hihat": Instrument.CLOSED_HIHAT,
    "closed_hi_hat": Instrument.CLOSED_HIHAT,
    "hihat": Instrument.CLOSED_HIHAT,
    "hi_hat": Instrument.CLOSED_HIHAT,
    "open_hihat": Instrument.OPEN_HIHAT,
    "open_hi_hat": Instrument.OPEN_HIHAT,
    "pedal_hihat": Instrument.PEDAL_HIHAT,
    "ride": Instrument.RIDE,
    "ride_bell": Instrument.RIDE_BELL,
    "crash": Instrument.CRASH,
    "high_tom": Instrument.HIGH_TOM,
    "mid_tom": Instrument.MID_TOM,
    "low_tom": Instrument.LOW_TOM,
    "floor_tom": Instrument.FLOOR_TOM,
}


def _number(item: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, int | float) and math.isfinite(float(value)):
            return float(value)
    return None


def _find_event_list(payload: Any, keys: set[str]) -> list[dict[str, Any]] | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.casefold() in keys and isinstance(value, list):
                rows = [item for item in value if isinstance(item, dict)]
                if rows:
                    return rows
        for value in payload.values():
            found = _find_event_list(value, keys)
            if found:
                return found
    return None


def _klangio_payload(response: httpx.Response) -> dict[str, Any]:
    if response.is_error:
        raise CommercialProviderError(
            _error_category(response.status_code),
            f"Klangio returned HTTP {response.status_code}",
            request_id=_request_id(response),
        )
    try:
        payload: Any = response.json()
        if isinstance(payload, str):
            payload = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CommercialProviderError(
            ProviderErrorCategory.INVALID_RESPONSE, "Klangio returned invalid JSON output"
        ) from exc
    if not isinstance(payload, dict):
        raise CommercialProviderError(
            ProviderErrorCategory.INVALID_RESPONSE, "Klangio output must be a JSON object"
        )
    return payload


class _KlangioBase:
    provider_id = "klangio"
    category = ProviderCategory.PRODUCTION_COMMERCIAL

    def __init__(
        self,
        config: CommercialHTTPConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._client = client

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={"kl-api-key": self.config.api_key},
            timeout=httpx.Timeout(self.config.timeout_seconds),
        )

    async def _poll(self, client: httpx.AsyncClient, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.timeout_seconds
        while True:
            status = _checked_json(await client.get(f"/job/{job_id}/status"))
            state = str(status.get("status") or "").casefold()
            if state in {"completed", "complete", "done", "finished", "success", "succeeded"}:
                return status
            if state in {"failed", "error", "cancelled", "canceled"}:
                raise CommercialProviderError(
                    ProviderErrorCategory.UPSTREAM_FAILURE,
                    f"Klangio job failed: {str(status.get('error') or state)[:300]}",
                    request_id=job_id,
                )
            if time.monotonic() >= deadline:
                raise CommercialProviderError(
                    ProviderErrorCategory.TIMEOUT, "Klangio job timed out", request_id=job_id
                )
            await asyncio.sleep(self.config.poll_interval_seconds)


class KlangioDrumTranscriptionProvider(_KlangioBase):
    async def transcribe(self, drum_audio: Path) -> DrumTranscriptionResult:
        started = time.monotonic()
        owns_client = self._client is None
        client = self._client or self._make_client()
        try:
            try:
                with drum_audio.open("rb") as handle:
                    created = _checked_json(
                        await client.post(
                            "/transcription",
                            params={"model": "drums"},
                            data={"outputs": "json"},
                            files={"file": (drum_audio.name, handle, "audio/wav")},
                        )
                    )
                job_id = str(created.get("job_id") or "")
                if not job_id:
                    raise CommercialProviderError(
                        ProviderErrorCategory.INVALID_RESPONSE,
                        "Klangio transcription response omitted job id",
                    )
                await self._poll(client, job_id)
                payload = _klangio_payload(await client.get(f"/job/{job_id}/json"))
            except httpx.TimeoutException as exc:
                raise CommercialProviderError(
                    ProviderErrorCategory.TIMEOUT, "Klangio transcription timed out"
                ) from exc
            except httpx.RequestError as exc:
                raise CommercialProviderError(
                    ProviderErrorCategory.UPSTREAM_FAILURE, "Klangio transcription request failed"
                ) from exc
            rows = _find_event_list(payload, {"hits", "events", "notes", "drums"})
            if not rows:
                raise CommercialProviderError(
                    ProviderErrorCategory.INVALID_RESPONSE,
                    "Klangio drum JSON contained no canonicalizable hit list",
                    request_id=job_id,
                )
            hits = tuple(self._hit(row) for row in rows)
            if not hits:
                raise CommercialProviderError(
                    ProviderErrorCategory.INVALID_RESPONSE,
                    "Klangio drum JSON contained no hits",
                    request_id=job_id,
                )
            return DrumTranscriptionResult(
                hits=hits,
                metadata=ProviderRunMetadata(
                    provider=self.provider_id,
                    category=self.category,
                    model_version="drums",
                    request_id=job_id,
                    processing_ms=round((time.monotonic() - started) * 1000),
                    raw_metadata=_sanitize_metadata(
                        {"job": created, "outputSummary": {"hitCount": len(hits)}}
                    ),
                    retention_expires_at=(
                        str(created["deletion_date"]) if created.get("deletion_date") else None
                    ),
                    contract_reference=self.config.contract_reference,
                ),
            )
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _hit(item: dict[str, Any]) -> RawDrumHit:
        onset = _number(item, "onsetSeconds", "onset_seconds", "onset", "time", "start")
        if onset is None or onset < 0:
            raise CommercialProviderError(
                ProviderErrorCategory.INVALID_RESPONSE, "Klangio hit has an invalid onset"
            )
        label = str(
            item.get("instrument")
            or item.get("instrumentClass")
            or item.get("instrument_class")
            or item.get("label")
            or ""
        )
        normalized = label.strip().casefold().replace("-", "_").replace(" ", "_")
        instrument = KLANGIO_INSTRUMENTS.get(normalized)
        if instrument is None:
            raise CommercialProviderError(
                ProviderErrorCategory.INVALID_RESPONSE,
                f"Klangio returned unsupported drum class {label!r}",
            )
        velocity = _number(item, "velocity", "midiVelocity", "midi_velocity")
        confidence = _number(item, "confidence", "probability", "score")
        raw_velocity = 100 if velocity is None else velocity * 127 if velocity <= 1 else velocity
        return RawDrumHit(
            instrument=instrument,
            onset_seconds=onset,
            velocity=max(1, min(127, round(raw_velocity))),
            confidence=max(0, min(1, 0.5 if confidence is None else confidence)),
        )


class KlangioBeatTrackingProvider(_KlangioBase):
    async def track(self, audio: Path) -> BeatTrackingResult:
        started = time.monotonic()
        owns_client = self._client is None
        client = self._client or self._make_client()
        try:
            try:
                with audio.open("rb") as handle:
                    created = _checked_json(
                        await client.post(
                            "/beat-tracking",
                            files={"file": (audio.name, handle, "audio/wav")},
                        )
                    )
                job_id = str(created.get("job_id") or "")
                if not job_id:
                    raise CommercialProviderError(
                        ProviderErrorCategory.INVALID_RESPONSE,
                        "Klangio beat-tracking response omitted job id",
                    )
                await self._poll(client, job_id)
                payload = _klangio_payload(await client.get(f"/job/{job_id}/json"))
            except httpx.TimeoutException as exc:
                raise CommercialProviderError(
                    ProviderErrorCategory.TIMEOUT, "Klangio beat tracking timed out"
                ) from exc
            except httpx.RequestError as exc:
                raise CommercialProviderError(
                    ProviderErrorCategory.UPSTREAM_FAILURE, "Klangio beat request failed"
                ) from exc
            rows = _find_event_list(payload, {"beats", "beat_positions", "beatpositions"})
            if not rows:
                raise CommercialProviderError(
                    ProviderErrorCategory.INVALID_RESPONSE,
                    "Klangio beat JSON contained no canonicalizable beat list",
                    request_id=job_id,
                )
            beats = self._beats(rows)
            downbeats = [beat for beat in beats if beat.is_downbeat]
            if not downbeats:
                raise CommercialProviderError(
                    ProviderErrorCategory.INVALID_RESPONSE,
                    "Klangio beat JSON did not identify any downbeats",
                    request_id=job_id,
                )
            segments = self._segments(payload, beats)
            confidence_values = [beat.confidence for beat in beats if beat.confidence is not None]
            confidence = (
                statistics.fmean(confidence_values) if confidence_values else None
            )
            return BeatTrackingResult(
                segments=segments,
                beats=beats,
                bar_one_seconds=downbeats[0].time_seconds,
                metadata=ProviderRunMetadata(
                    provider=self.provider_id,
                    category=self.category,
                    model_version="beat-tracking/0.2",
                    request_id=job_id,
                    processing_ms=round((time.monotonic() - started) * 1000),
                    confidence=confidence,
                    raw_metadata=_sanitize_metadata(
                        {
                            "job": created,
                            "outputSummary": {
                                "beatCount": len(beats),
                                "downbeatCount": len(downbeats),
                            },
                        }
                    ),
                    retention_expires_at=(
                        str(created["deletion_date"]) if created.get("deletion_date") else None
                    ),
                    contract_reference=self.config.contract_reference,
                ),
            )
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _beats(rows: list[dict[str, Any]]) -> tuple[Beat, ...]:
        beats: list[Beat] = []
        measure = 0
        for index, item in enumerate(rows):
            timestamp = _number(item, "timeSeconds", "time_seconds", "time", "start", "onset")
            if timestamp is None or timestamp < 0:
                raise CommercialProviderError(
                    ProviderErrorCategory.INVALID_RESPONSE, "Klangio beat has an invalid time"
                )
            beat_in_measure_value = _number(
                item, "beatInMeasure", "beat_in_measure", "beat", "position"
            )
            downbeat = bool(item.get("isDownbeat") or item.get("is_downbeat"))
            beat_in_measure = round(beat_in_measure_value or (1 if downbeat else index % 4 + 1))
            if downbeat and beats:
                measure += 1
                beat_in_measure = 1
            explicit_measure = _number(item, "measureIndex", "measure_index", "measure")
            if explicit_measure is not None:
                measure = max(0, round(explicit_measure))
            confidence = _number(item, "confidence", "probability", "score")
            beats.append(
                Beat(
                    time_seconds=timestamp,
                    beat_in_measure=max(1, beat_in_measure),
                    measure_index=measure,
                    is_downbeat=downbeat,
                    confidence=max(0, min(1, confidence)) if confidence is not None else None,
                )
            )
        return tuple(sorted(beats, key=lambda item: item.time_seconds))

    @staticmethod
    def _segments(payload: dict[str, Any], beats: tuple[Beat, ...]) -> tuple[TempoSegment, ...]:
        rows = _find_event_list(payload, {"segments", "tempo_map", "tempomap"}) or []
        segments: list[TempoSegment] = []
        for item in rows:
            bpm = _number(item, "bpm", "tempo")
            start = _number(item, "startSeconds", "start_seconds", "start", "time")
            if bpm is None or start is None or bpm < 20 or bpm > 400 or start < 0:
                continue
            numerator = round(_number(item, "timeSignatureNumerator", "numerator") or 4)
            denominator = round(_number(item, "timeSignatureDenominator", "denominator") or 4)
            start_measure = round(_number(item, "startMeasure", "start_measure") or 0)
            segments.append(
                TempoSegment(start, bpm, numerator, denominator, max(0, start_measure))
            )
        if segments:
            return tuple(sorted(segments, key=lambda item: item.start_seconds))
        intervals = [
            later.time_seconds - earlier.time_seconds
            for earlier, later in pairwise(beats)
            if later.time_seconds > earlier.time_seconds
        ]
        if not intervals:
            raise CommercialProviderError(
                ProviderErrorCategory.INVALID_RESPONSE,
                "Klangio beat output did not contain enough beats to derive tempo",
            )
        bpm = 60 / statistics.median(intervals)
        if bpm < 20 or bpm > 400:
            raise CommercialProviderError(
                ProviderErrorCategory.INVALID_RESPONSE, "Klangio derived tempo is out of range"
            )
        numerator = max(1, max(beat.beat_in_measure for beat in beats))
        denominator = 8 if numerator in {6, 12} else 4
        return (TempoSegment(beats[0].time_seconds, bpm, numerator, denominator, 0),)
