from __future__ import annotations

from types import SimpleNamespace

import pytest
from drumscribe_music import (
    ADTOFResearchTranscriptionProvider,
    DrumScribeHybridTranscriptionProvider,
    DrumScribeRecallFusionTranscriptionProvider,
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
        DrumScribeRecallFusionTranscriptionProvider=DrumScribeRecallFusionTranscriptionProvider,
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
        (
            "drumscribe_recall_fusion",
            "recall_fusion_command",
            DrumScribeRecallFusionTranscriptionProvider,
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


def test_owner_approved_self_hosted_pipeline_can_be_selected_in_production() -> None:
    settings = Settings(
        environment=Environment.PRODUCTION,
        database_url="postgresql+asyncpg://db.test/drumscribe",
        storage_backend="s3",
        queue_backend="celery",
        pipeline_provider="music_engine",
        source_separation_provider="demucs",
        music_transcription_provider="adtof",
        beat_tracking_provider="research",
        commercial_provider_license_confirmed=True,
        commercial_provider_approval_reference="OWNER-ATTESTATION-2026-09-05",
        adtof_command="/approved/adtof",
        adtof_model_version="adtof-pytorch-85c192e78f71",
        cookie_secure=True,
        dev_expose_magic_link=False,
        magic_link_delivery="webhook",
        magic_link_webhook_url="https://mail.test/link",
        session_secret="a" * 40,
        s3_access_key_id="access",
        s3_secret_access_key="secret",
        allowed_hosts=["api.drumscribe.test"],
    )
    assert settings.source_separation_provider == "demucs"
    assert settings.music_transcription_provider == "adtof"
    assert settings.beat_tracking_provider == "research"


def test_owner_approved_recall_fusion_can_be_selected_in_production() -> None:
    settings = Settings(
        environment=Environment.PRODUCTION,
        database_url="postgresql+asyncpg://db.test/drumscribe",
        storage_backend="s3",
        queue_backend="celery",
        pipeline_provider="music_engine",
        source_separation_provider="demucs",
        music_transcription_provider="drumscribe_recall_fusion",
        beat_tracking_provider="research",
        commercial_provider_license_confirmed=True,
        commercial_provider_approval_reference="OWNER-ATTESTATION-2026-09-05",
        recall_fusion_command="/approved/recall-fusion",
        recall_fusion_model_version="drumscribe-recall-fusion-v2",
        cookie_secure=True,
        dev_expose_magic_link=False,
        magic_link_delivery="webhook",
        magic_link_webhook_url="https://mail.test/link",
        session_secret="a" * 40,
        s3_access_key_id="access",
        s3_secret_access_key="secret",
        allowed_hosts=["api.drumscribe.test"],
    )
    assert settings.music_transcription_provider == "drumscribe_recall_fusion"


def test_production_rejects_an_unapproved_adtof_version() -> None:
    with pytest.raises(ValueError, match="ADTOF model version is not approved"):
        Settings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+asyncpg://db.test/drumscribe",
            storage_backend="s3",
            queue_backend="celery",
            pipeline_provider="music_engine",
            source_separation_provider="demucs",
            music_transcription_provider="adtof",
            beat_tracking_provider="research",
            commercial_provider_license_confirmed=True,
            commercial_provider_approval_reference="OWNER-ATTESTATION-2026-09-05",
            adtof_command="/approved/adtof",
            adtof_model_version="different-version",
            cookie_secure=True,
            dev_expose_magic_link=False,
            magic_link_delivery="webhook",
            magic_link_webhook_url="https://mail.test/link",
            session_secret="a" * 40,
            s3_access_key_id="access",
            s3_secret_access_key="secret",
            allowed_hosts=["api.drumscribe.test"],
        )


def test_self_hosted_production_rejects_an_unrelated_approval_reference() -> None:
    with pytest.raises(ValueError, match="pinned owner approval reference"):
        Settings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+asyncpg://db.test/drumscribe",
            storage_backend="s3",
            queue_backend="celery",
            pipeline_provider="music_engine",
            source_separation_provider="demucs",
            music_transcription_provider="adtof",
            beat_tracking_provider="research",
            commercial_provider_license_confirmed=True,
            commercial_provider_approval_reference="unrelated-review",
            adtof_command="/approved/adtof",
            adtof_model_version="adtof-pytorch-85c192e78f71",
            cookie_secure=True,
            dev_expose_magic_link=False,
            magic_link_delivery="webhook",
            magic_link_webhook_url="https://mail.test/link",
            session_secret="a" * 40,
            s3_access_key_id="access",
            s3_secret_access_key="secret",
            allowed_hosts=["api.drumscribe.test"],
        )
