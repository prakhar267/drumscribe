from __future__ import annotations

from types import SimpleNamespace

import pytest
from drumscribe_music import (
    ADTOFResearchTranscriptionProvider,
    DrumScribeHybridTranscriptionProvider,
    OaFDrumsTranscriptionProvider,
    YourMT3PlusTranscriptionProvider,
)

from drumscribe_api.config import Settings
from drumscribe_api.enums import Environment
from drumscribe_api.services.pipeline import MusicEngineAdapter


def research_engine() -> SimpleNamespace:
    return SimpleNamespace(
        YourMT3PlusTranscriptionProvider=YourMT3PlusTranscriptionProvider,
        OaFDrumsTranscriptionProvider=OaFDrumsTranscriptionProvider,
        ADTOFResearchTranscriptionProvider=ADTOFResearchTranscriptionProvider,
        DrumScribeHybridTranscriptionProvider=DrumScribeHybridTranscriptionProvider,
    )


@pytest.mark.parametrize(
    ("provider_name", "setting", "provider_type", "input_kind"),
    [
        ("yourmt3_plus", "yourmt3_command", YourMT3PlusTranscriptionProvider, "full_mix"),
        ("oaf_drums", "oaf_drums_command", OaFDrumsTranscriptionProvider, "drum_stem"),
        ("adtof", "adtof_command", ADTOFResearchTranscriptionProvider, "drum_stem"),
        (
            "drumscribe_hybrid",
            "hybrid_command",
            DrumScribeHybridTranscriptionProvider,
            "drum_stem",
        ),
    ],
)
def test_research_model_selection_uses_argv_without_a_shell(
    monkeypatch, provider_name, setting, provider_type, input_kind
):
    settings = Settings(
        pipeline_provider="music_engine",
        music_transcription_provider=provider_name,
        **{setting: '/safe/python "/runner with spaces.py"'},
    )
    adapter = MusicEngineAdapter(settings)
    monkeypatch.setattr(adapter, "_engine", research_engine)
    provider = adapter._transcription_provider(research_engine())
    assert isinstance(provider, provider_type)
    assert provider.command == ("/safe/python", "/runner with spaces.py")
    assert adapter.transcription_input_kind() == input_kind


def test_research_model_selection_requires_an_explicit_command() -> None:
    settings = Settings(
        pipeline_provider="music_engine",
        music_transcription_provider="yourmt3_plus",
        yourmt3_command=None,
    )
    with pytest.raises(RuntimeError, match="model command"):
        MusicEngineAdapter(settings)._transcription_provider(research_engine())


def test_adtof_cannot_be_selected_in_production() -> None:
    with pytest.raises(ValueError, match="commercially approved Klangio drum adapter"):
        Settings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+asyncpg://db.test/drumscribe",
            storage_backend="s3",
            queue_backend="celery",
            pipeline_provider="music_engine",
            source_separation_provider="audioshake",
            music_transcription_provider="adtof",
            beat_tracking_provider="klangio",
            commercial_provider_license_confirmed=True,
            commercial_provider_approval_reference="legal-review",
            audioshake_api_key="key",
            audioshake_contract_reference="contract",
            klangio_api_key="key",
            klangio_contract_reference="contract",
            adtof_command="/research/adtof",
            cookie_secure=True,
            dev_expose_magic_link=False,
            magic_link_delivery="webhook",
            magic_link_webhook_url="https://mail.test/link",
            session_secret="a" * 40,
            s3_access_key_id="access",
            s3_secret_access_key="secret",
            allowed_hosts=["api.drumscribe.test"],
        )
