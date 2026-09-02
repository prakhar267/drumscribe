import json
import os
import subprocess
from pathlib import Path

import pytest

from drumscribe_music import (
    ADTOFResearchTranscriptionProvider,
    CommercialProviderConfig,
    DemucsAdapter,
    DrumScribeHybridTranscriptionProvider,
    ExternalModelError,
    MockBeatTrackingProvider,
    MockDrumTranscriptionProvider,
    OaFDrumsTranscriptionProvider,
    PassthroughSourceSeparationProvider,
    RawDrumHit,
    ResearchDependencyError,
    ResearchDrumTranscriptionProvider,
    TempoMap,
    UnsafeProviderError,
    YourMT3PlusTranscriptionProvider,
    require_production_safe,
    validate_provider_registry,
)
from drumscribe_music.providers.research import (
    ResearchBeatThisTrackingProvider,
    _classify_features,
    _classify_spectrum,
    _tempo_map_from_observed_beats,
)


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


def test_research_multiclass_mapping_uses_spectral_and_decay_evidence():
    base = {
        "lowRatio": 0.02,
        "lowMidRatio": 0.16,
        "midRatio": 0.18,
        "highMidRatio": 0.31,
        "highRatio": 0.29,
        "centroid": 0.16,
        "flatness": 0.53,
        "decay": -0.5,
        "zeroCrossingRate": 0.08,
        "dominantBodyHz": 180,
    }
    assert _classify_features(base)[0].value == "SNARE"
    assert _classify_features({**base, "lowRatio": 0.4})[0].value == "KICK"
    assert (
        _classify_features(
            {
                **base,
                "lowRatio": 0.18,
                "lowMidRatio": 0.23,
                "midRatio": 0.21,
                "highRatio": 0.12,
                "centroid": 0.08,
                "flatness": 0.28,
                "dominantBodyHz": 95,
            }
        )[0].value
        == "FLOOR_TOM"
    )
    assert (
        _classify_features(
            {
                **base,
                "lowMidRatio": 0.06,
                "midRatio": 0.04,
                "highRatio": 0.5,
                "zeroCrossingRate": 0.2,
            }
        )[0].value
        == "CLOSED_HIHAT"
    )
    assert (
        _classify_features(
            {
                **base,
                "lowMidRatio": 0.08,
                "midRatio": 0.08,
                "highRatio": 0.33,
                "decay": 0.0,
            }
        )[0].value
        == "CRASH"
    )
    assert (
        _classify_features(
            {
                **base,
                "lowMidRatio": 0.07,
                "midRatio": 0.07,
                "highRatio": 0.4,
                "flatness": 0.48,
                "decay": -1.2,
                "zeroCrossingRate": 0.25,
            }
        )[0].value
        == "TAMBOURINE"
    )


def test_accurate_research_tracker_preserves_beats_downbeats_and_meter():
    tempo_map = _tempo_map_from_observed_beats(
        [0.02, 0.54, 1.08, 1.64, 2.20, 2.74, 3.30, 3.84, 4.38],
        [0.02, 2.20, 4.38],
    )

    assert tempo_map.time_signatures[0].numerator == 4
    assert tempo_map.offset_seconds == pytest.approx(0.02)
    assert tempo_map.beat_to_seconds(4) == pytest.approx(2.20)
    assert tempo_map.beat_to_seconds(8) == pytest.approx(4.38)


def test_accurate_research_tracker_remains_blocked_in_production():
    provider = ResearchBeatThisTrackingProvider(device="cpu")
    assert provider.version == "beat-this/final0"
    with pytest.raises(UnsafeProviderError):
        require_production_safe(provider, production=True)


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
        result = output_root / "htdemucs_ft" / source.stem / "drums.wav"
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


@pytest.mark.parametrize(
    ("provider_class", "license_status", "input_kind"),
    [
        (YourMT3PlusTranscriptionProvider, "unresolved", "full_mix"),
        (OaFDrumsTranscriptionProvider, "unresolved", "drum_stem"),
        (ADTOFResearchTranscriptionProvider, "non_commercial", "drum_stem"),
        (DrumScribeHybridTranscriptionProvider, "unresolved", "drum_stem"),
    ],
)
def test_external_research_models_are_license_gated(provider_class, license_status, input_kind):
    provider = provider_class(("/safe/runner",), model_version="test")
    assert provider.license.status.value == license_status
    assert provider.input_kind == input_kind
    with pytest.raises(UnsafeProviderError):
        require_production_safe(provider, production=True)
    require_production_safe(provider, production=False)


def test_external_model_contract_is_argv_safe_and_validated(monkeypatch, tmp_path):
    source = tmp_path / "mix; touch NEVER.wav"
    source.write_bytes(b"audio")
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed["kwargs"] = kwargs
        output = Path(argv[argv.index("--output") + 1])
        output.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "provider": "research-yourmt3-plus-v1",
                    "hits": [
                        {
                            "instrument": 38,
                            "onsetSeconds": 0.51,
                            "velocity": 112,
                            "confidence": 0.91,
                        },
                        {"instrument": "kick", "onsetSeconds": 0.01},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(argv, 0, stdout=b"ignored", stderr=b"")

    monkeypatch.setattr("drumscribe_music.providers.external.subprocess.run", fake_run)
    provider = YourMT3PlusTranscriptionProvider(
        ("/safe/python", "/safe/runner.py"), model_version="yptf-moe"
    )
    hits = provider.transcribe(source)
    assert [item.instrument_class.value for item in hits] == ["KICK", "SNARE"]
    assert observed["argv"][-4:-2] == ("--input", os.fspath(source.resolve()))
    assert observed["kwargs"]["shell"] is False
    assert len([item for item in observed["argv"] if "touch" in item]) == 1


def test_external_model_contract_rejects_wrong_provider(monkeypatch, tmp_path):
    source = tmp_path / "mix.wav"
    source.write_bytes(b"audio")

    def fake_run(argv, **kwargs):
        del kwargs
        output = Path(argv[argv.index("--output") + 1])
        output.write_text('{"schemaVersion":1,"provider":"wrong","hits":[]}', encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr("drumscribe_music.providers.external.subprocess.run", fake_run)
    provider = OaFDrumsTranscriptionProvider(("/safe/runner",), model_version="checkpoint")
    with pytest.raises(ExternalModelError, match="does not match"):
        provider.transcribe(source)


def test_commercial_config_fails_closed():
    with pytest.raises(ValueError, match="HTTPS"):
        CommercialProviderConfig("vendor", "http://vendor.test", "secret", "contract")
    with pytest.raises(ValueError, match="confirmation"):
        CommercialProviderConfig("vendor", "https://vendor.test", "secret", "contract")
    configured = CommercialProviderConfig(
        "vendor", "https://vendor.test/v1", "secret", "MSA-123", commercial_license_confirmed=True
    )
    assert configured.contract_reference == "MSA-123"
