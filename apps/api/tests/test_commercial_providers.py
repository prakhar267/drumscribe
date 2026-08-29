from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from drumscribe_api.config import Settings
from drumscribe_api.enums import Environment, Instrument
from drumscribe_api.services.commercial_providers import (
    AudioShakeSourceSeparationProvider,
    CommercialHTTPConfig,
    KlangioBeatTrackingProvider,
    KlangioDrumTranscriptionProvider,
    MusicAISourceSeparationProvider,
)
from drumscribe_api.services.pipeline_contracts import ProviderCategory


def provider_config(base_url: str = "https://provider.test") -> CommercialHTTPConfig:
    return CommercialHTTPConfig(
        api_key="test-key",
        contract_reference="legal-approval-2026-08",
        base_url=base_url,
        timeout_seconds=5,
        poll_interval_seconds=0,
    )


@pytest.mark.asyncio
async def test_audioshake_adapter_uploads_polls_downloads_and_records_cost(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mix.wav"
    source.write_bytes(b"source-audio")
    destination = tmp_path / "drums.wav"
    task_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal task_reads
        if request.method == "POST" and request.url.path == "/assets":
            assert request.headers["x-api-key"] == "test-key"
            return httpx.Response(200, json={"id": "asset-1", "format": "wav"})
        if request.method == "POST" and request.url.path == "/tasks":
            payload = json.loads(request.content)
            assert payload["targets"] == [{"model": "drums", "formats": ["wav"]}]
            return httpx.Response(
                200,
                json={
                    "id": "task-1",
                    "cost": 3,
                    "targets": [
                        {
                            "model": "drums",
                            "status": "processing",
                            "output": [],
                            "cost": 3,
                        }
                    ],
                },
            )
        if request.method == "GET" and request.url.path == "/tasks/task-1":
            task_reads += 1
            return httpx.Response(
                200,
                json={
                    "id": "task-1",
                    "cost": 3,
                    "targets": [
                        {
                            "model": "drums",
                            "status": "completed",
                            "output": [
                                {
                                    "name": "drums.wav",
                                    "format": "wav",
                                    "link": "https://cdn.test/drums.wav?secret=signed",
                                }
                            ],
                            "cost": 3,
                        }
                    ],
                },
            )
        if request.method == "GET" and request.url.host == "cdn.test":
            return httpx.Response(200, content=b"real-provider-stem")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with httpx.AsyncClient(
        base_url="https://provider.test",
        headers={"x-api-key": "test-key"},
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await AudioShakeSourceSeparationProvider(
            provider_config(), client=client
        ).separate_drums(source, destination)

    assert task_reads == 1
    assert destination.read_bytes() == b"real-provider-stem"
    assert result.metadata.category is ProviderCategory.PRODUCTION_COMMERCIAL
    assert result.metadata.request_id == "task-1"
    assert result.metadata.cost_amount == 3
    assert result.metadata.cost_currency == "AudioShake credits"
    assert "link" not in json.dumps(result.metadata.raw_metadata).casefold()


@pytest.mark.asyncio
async def test_music_ai_adapter_uses_signed_upload_and_configured_result_key(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mix.wav"
    source.write_bytes(b"music-ai-source")
    destination = tmp_path / "drums.wav"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/upload":
            return httpx.Response(
                200,
                json={
                    "uploadUrl": "https://uploads.test/object",
                    "downloadUrl": "https://uploads.test/input",
                },
            )
        if request.method == "PUT" and request.url.host == "uploads.test":
            return httpx.Response(200)
        if request.method == "POST" and request.url.path == "/v1/job":
            payload = json.loads(request.content)
            assert payload["workflow"] == "workspace/drum-separation"
            return httpx.Response(200, json={"id": "music-job-1"})
        if request.method == "GET" and request.url.path == "/v1/job/music-job-1":
            return httpx.Response(
                200,
                json={
                    "id": "music-job-1",
                    "status": "SUCCEEDED",
                    "workflow": "workspace/drum-separation",
                    "result": {"drumStem": "https://cdn.test/music-ai-drums.wav"},
                },
            )
        if request.method == "GET" and request.url.host == "cdn.test":
            return httpx.Response(200, content=b"music-ai-stem")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with httpx.AsyncClient(
        base_url="https://api.music.test/v1",
        headers={"Authorization": "test-key"},
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await MusicAISourceSeparationProvider(
            provider_config("https://api.music.test/v1"),
            workflow="workspace/drum-separation",
            result_key="drumStem",
            client=client,
        ).separate_drums(source, destination)

    assert destination.read_bytes() == b"music-ai-stem"
    assert result.metadata.request_id == "music-job-1"
    assert result.metadata.model_version == "workspace/drum-separation"


@pytest.mark.asyncio
async def test_klangio_drum_adapter_normalizes_simultaneous_multilabel_hits(
    tmp_path: Path,
) -> None:
    source = tmp_path / "drums.wav"
    source.write_bytes(b"drum-stem")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["kl-api-key"] == "test-key"
        if request.method == "POST" and request.url.path == "/transcription":
            assert request.url.params["model"] == "drums"
            return httpx.Response(
                200,
                json={
                    "job_id": "job-1",
                    "creation_date": "2026-08-29",
                    "deletion_date": "2026-09-05",
                    "status_endpoint_url": "/job/job-1/status",
                },
            )
        if request.method == "GET" and request.url.path == "/job/job-1/status":
            return httpx.Response(200, json={"status": "completed"})
        if request.method == "GET" and request.url.path == "/job/job-1/json":
            return httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "instrument": "kick",
                            "onsetSeconds": 0.493,
                            "velocity": 94,
                            "confidence": 0.97,
                        },
                        {
                            "instrument": "closed hi hat",
                            "onsetSeconds": 0.493,
                            "velocity": 0.54,
                            "confidence": 0.91,
                        },
                    ]
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with httpx.AsyncClient(
        base_url="https://provider.test",
        headers={"kl-api-key": "test-key"},
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await KlangioDrumTranscriptionProvider(
            provider_config(), client=client
        ).transcribe(source)

    assert [hit.instrument for hit in result.hits] == [
        Instrument.KICK,
        Instrument.CLOSED_HIHAT,
    ]
    assert result.hits[0].onset_seconds == result.hits[1].onset_seconds
    assert result.hits[1].velocity == 69
    assert result.metadata.request_id == "job-1"
    assert result.metadata.retention_expires_at == "2026-09-05"


@pytest.mark.asyncio
async def test_klangio_beat_adapter_requires_downbeats_and_builds_canonical_grid(
    tmp_path: Path,
) -> None:
    source = tmp_path / "drums.wav"
    source.write_bytes(b"drum-stem")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/beat-tracking":
            return httpx.Response(
                200,
                json={
                    "job_id": "beat-1",
                    "creation_date": "2026-08-29",
                    "deletion_date": "2026-09-05",
                    "status_endpoint_url": "/job/beat-1/status",
                },
            )
        if request.method == "GET" and request.url.path == "/job/beat-1/status":
            return httpx.Response(200, json={"status": "completed"})
        if request.method == "GET" and request.url.path == "/job/beat-1/json":
            return httpx.Response(
                200,
                json={
                    "beats": [
                        {
                            "timeSeconds": 0.2,
                            "beatInMeasure": 1,
                            "measureIndex": 0,
                            "isDownbeat": True,
                            "confidence": 0.9,
                        },
                        {
                            "timeSeconds": 0.7,
                            "beatInMeasure": 2,
                            "measureIndex": 0,
                            "isDownbeat": False,
                            "confidence": 0.8,
                        },
                        {
                            "timeSeconds": 1.2,
                            "beatInMeasure": 3,
                            "measureIndex": 0,
                            "isDownbeat": False,
                            "confidence": 0.85,
                        },
                    ],
                    "tempoMap": [
                        {
                            "startSeconds": 0.2,
                            "bpm": 120,
                            "timeSignatureNumerator": 4,
                            "timeSignatureDenominator": 4,
                            "startMeasure": 0,
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with httpx.AsyncClient(
        base_url="https://provider.test",
        headers={"kl-api-key": "test-key"},
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await KlangioBeatTrackingProvider(provider_config(), client=client).track(source)

    assert result.bar_one_seconds == 0.2
    assert result.segments[0].bpm == 120
    assert result.beats[0].is_downbeat is True


def production_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": Environment.PRODUCTION,
        "database_url": "postgresql+asyncpg://db.test/drumscribe",
        "storage_backend": "s3",
        "queue_backend": "celery",
        "pipeline_provider": "music_engine",
        "source_separation_provider": "audioshake",
        "music_transcription_provider": "klangio_drums",
        "beat_tracking_provider": "klangio",
        "commercial_provider_license_confirmed": True,
        "commercial_provider_approval_reference": "legal-2026-08",
        "audioshake_api_key": "audio-key",
        "audioshake_contract_reference": "audio-contract",
        "klangio_api_key": "klangio-key",
        "klangio_contract_reference": "klangio-contract",
        "cookie_secure": True,
        "dev_expose_magic_link": False,
        "magic_link_delivery": "webhook",
        "magic_link_webhook_url": "https://mail.test/magic-link",
        "session_secret": "a" * 40,
        "s3_access_key_id": "access",
        "s3_secret_access_key": "secret",
        "allowed_hosts": ["api.drumscribe.test"],
    }
    values.update(overrides)
    return Settings(**values)


def test_production_configuration_fails_closed_for_fixture_and_missing_approval() -> None:
    production_settings()
    with pytest.raises(ValueError, match="deterministic development pipeline"):
        production_settings(pipeline_provider="development")
    with pytest.raises(ValueError, match="explicit commercial approval"):
        production_settings(commercial_provider_license_confirmed=False)
    with pytest.raises(ValueError, match="commercially approved Klangio drum adapter"):
        production_settings(music_transcription_provider="mock")


@pytest.mark.asyncio
async def test_production_drum_adapter_does_not_return_duration_derived_fixture(
    tmp_path: Path,
) -> None:
    inputs = [tmp_path / "a.wav", tmp_path / "b.wav"]
    for path in inputs:
        path.write_bytes(b"same-duration-different-recording")
    created_jobs = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal created_jobs
        if request.method == "POST" and request.url.path == "/transcription":
            created_jobs += 1
            return httpx.Response(
                200,
                json={
                    "job_id": f"job-{created_jobs}",
                    "creation_date": "2026-08-29",
                    "deletion_date": "2026-09-05",
                    "status_endpoint_url": f"/job/job-{created_jobs}/status",
                },
            )
        if request.method == "GET" and request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "completed"})
        if request.method == "GET" and request.url.path.endswith("/json"):
            job_number = int(request.url.path.split("-")[1].split("/")[0])
            instrument = "kick" if job_number == 1 else "snare"
            onset = 0.17 if job_number == 1 else 0.43
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "instrument": instrument,
                            "onsetSeconds": onset,
                            "velocity": 100,
                            "confidence": 0.9,
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with httpx.AsyncClient(
        base_url="https://provider.test",
        headers={"kl-api-key": "test-key"},
        transport=httpx.MockTransport(handler),
    ) as client:
        provider = KlangioDrumTranscriptionProvider(provider_config(), client=client)
        first = await provider.transcribe(inputs[0])
        second = await provider.transcribe(inputs[1])

    assert first.hits != second.hits
    assert first.metadata.category is ProviderCategory.PRODUCTION_COMMERCIAL
    assert second.metadata.category is ProviderCategory.PRODUCTION_COMMERCIAL
