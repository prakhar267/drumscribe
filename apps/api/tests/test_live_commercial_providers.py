from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from drumscribe_api.services.commercial_providers import (
    AudioShakeSourceSeparationProvider,
    CommercialHTTPConfig,
    KlangioBeatTrackingProvider,
    KlangioDrumTranscriptionProvider,
)

pytestmark = [
    pytest.mark.live_ml,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_ML_TESTS") != "1",
        reason="paid live-provider tests require RUN_LIVE_ML_TESTS=1",
    ),
]


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.fail(f"{name} is required when RUN_LIVE_ML_TESTS=1")
    return value


def resolve_audio_fixture(raw_path: str) -> Path:
    path = Path(raw_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


@pytest.mark.asyncio
async def test_rights_cleared_audio_through_live_commercial_pipeline(tmp_path: Path) -> None:
    try:
        source = await asyncio.to_thread(
            resolve_audio_fixture, required_env("DRUMSCRIBE_LIVE_TEST_AUDIO")
        )
    except FileNotFoundError:
        pytest.fail("DRUMSCRIBE_LIVE_TEST_AUDIO must name a rights-cleared audio file")

    timeout = float(os.getenv("DRUMSCRIBE_PROVIDER_TIMEOUT_SECONDS", "600"))
    poll = float(os.getenv("DRUMSCRIBE_PROVIDER_POLL_INTERVAL_SECONDS", "2"))
    separation = AudioShakeSourceSeparationProvider(
        CommercialHTTPConfig(
            api_key=required_env("DRUMSCRIBE_AUDIOSHAKE_API_KEY"),
            contract_reference=required_env("DRUMSCRIBE_AUDIOSHAKE_CONTRACT_REFERENCE"),
            base_url=os.getenv(
                "DRUMSCRIBE_AUDIOSHAKE_API_URL", "https://api.audioshake.ai"
            ),
            timeout_seconds=timeout,
            poll_interval_seconds=poll,
        ),
        model=os.getenv("DRUMSCRIBE_AUDIOSHAKE_SEPARATION_MODEL", "drums"),
    )
    klangio_config = CommercialHTTPConfig(
        api_key=required_env("DRUMSCRIBE_KLANGIO_API_KEY"),
        contract_reference=required_env("DRUMSCRIBE_KLANGIO_CONTRACT_REFERENCE"),
        base_url=os.getenv("DRUMSCRIBE_KLANGIO_API_URL", "https://api.klang.io"),
        timeout_seconds=timeout,
        poll_interval_seconds=poll,
    )

    stem = tmp_path / "drums.wav"
    separated = await separation.separate_drums(source, stem)
    transcription = await KlangioDrumTranscriptionProvider(klangio_config).transcribe(stem)
    timing = await KlangioBeatTrackingProvider(klangio_config).track(stem)

    assert (await asyncio.to_thread(stem.stat)).st_size > 0
    assert separated.metadata.request_id
    assert transcription.metadata.request_id
    assert transcription.hits
    assert all(0 <= hit.onset_seconds for hit in transcription.hits)
    assert timing.metadata.request_id
    assert timing.beats
    assert any(beat.is_downbeat for beat in timing.beats)
