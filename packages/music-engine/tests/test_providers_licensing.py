import os
import subprocess
from pathlib import Path

import pytest

from drumscribe_music import (
    CommercialProviderConfig,
    DemucsAdapter,
    MockBeatTrackingProvider,
    MockDrumTranscriptionProvider,
    PassthroughSourceSeparationProvider,
    RawDrumHit,
    ResearchDependencyError,
    ResearchDrumTranscriptionProvider,
    TempoMap,
    UnsafeProviderError,
    require_production_safe,
    validate_provider_registry,
)
from drumscribe_music.providers.research import _classify_spectrum


def test_mock_provider_is_deterministic_and_protocol_friendly(tmp_path):
    audio = tmp_path / "anything.wav"
    audio.write_bytes(b"fixture")
    hits = [RawDrumHit("kick", 0.5)]
    provider = MockDrumTranscriptionProvider(hits)
    assert provider.transcribe(audio) == hits
    assert provider.transcribe(audio) is not provider.transcribe(audio)
    require_production_safe(provider)


def test_research_provider_is_blocked_in_production_but_allowed_locally():
    provider = ResearchDrumTranscriptionProvider()
    with pytest.raises(UnsafeProviderError, match="unresolved"):
        require_production_safe(provider, production=True)
    require_production_safe(provider, production=False)


def test_research_provider_explains_missing_optional_dependencies(monkeypatch, tmp_path):
    audio = tmp_path / "research.wav"
    audio.write_bytes(b"fixture")

    def missing_dependency(name):
        raise ImportError(name)

    monkeypatch.setattr(
        "drumscribe_music.providers.research.importlib.import_module", missing_dependency
    )
    with pytest.raises(ResearchDependencyError, match="\\[audio\\]"):
        ResearchDrumTranscriptionProvider().transcribe(audio)


def test_research_spectral_mapping_is_deliberately_conservative():
    assert _classify_spectrum(0.4, 0.1)[0].value == "KICK"
    assert _classify_spectrum(0.1, 0.4)[0].value == "CLOSED_HIHAT"
    assert _classify_spectrum(0.1, 0.1)[0].value == "SNARE"


def test_mock_beat_and_passthrough_separation(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio fixture")
    tempo = TempoMap.constant(98)
    assert MockBeatTrackingProvider(tempo).track(source) is tempo
    destination = tmp_path / "nested" / "drums.wav"
    assert PassthroughSourceSeparationProvider().separate_drums(source, destination) == destination
    assert destination.read_bytes() == source.read_bytes()


def test_demucs_adapter_is_process_isolated_and_argv_safe(monkeypatch, tmp_path):
    source = tmp_path / "mix; touch NEVER.wav"
    source.write_bytes(b"input")
    destination = tmp_path / "drums.wav"
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        output_root = Path(argv[argv.index("--out") + 1])
        result = output_root / "htdemucs" / source.stem / "drums.wav"
        result.parent.mkdir(parents=True)
        result.write_bytes(b"separated")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr("drumscribe_music.providers.demucs.subprocess.run", fake_run)
    result = DemucsAdapter(python_executable="/safe/python").separate_drums(source, destination)
    assert result.read_bytes() == b"separated"
    assert observed["argv"][-1] == os.fspath(source.resolve())
    assert len([item for item in observed["argv"] if "touch" in item]) == 1
    assert observed["argv"][:3] == ("/safe/python", "-m", "demucs.separate")
    with pytest.raises(ValueError, match="model"):
        DemucsAdapter(model="htdemucs; unsafe")


def test_provider_registry_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="duplicate"):
        validate_provider_registry(
            [MockDrumTranscriptionProvider(), MockDrumTranscriptionProvider()],
            production=True,
        )


def test_commercial_config_fails_closed():
    with pytest.raises(ValueError, match="HTTPS"):
        CommercialProviderConfig("vendor", "http://vendor.test", "secret", "contract")
    with pytest.raises(ValueError, match="confirmation"):
        CommercialProviderConfig("vendor", "https://vendor.test", "secret", "contract")
    configured = CommercialProviderConfig(
        "vendor", "https://vendor.test/v1", "secret", "MSA-123", commercial_license_confirmed=True
    )
    assert configured.contract_reference == "MSA-123"
