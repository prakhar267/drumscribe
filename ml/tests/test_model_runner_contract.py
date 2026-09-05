import hashlib
import importlib.util
import json
from pathlib import Path

import mido
import pytest


def _contract_module():
    path = Path(__file__).resolve().parents[2] / "scripts/model_runners/_midi_contract.py"
    spec = importlib.util.spec_from_file_location("drumscribe_midi_contract", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_module(filename: str, name: str):
    path = Path(__file__).resolve().parents[2] / "scripts/model_runners" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_full_mix_converter_only_accepts_general_midi_drum_channel(tmp_path):
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.Message("note_on", channel=0, note=36, velocity=100, time=0))
    track.append(mido.Message("note_on", channel=9, note=38, velocity=110, time=120))
    path = tmp_path / "mixture.mid"
    midi.save(path)
    hits = _contract_module().midi_hits(path)
    assert [(hit["instrument"], hit["velocity"]) for hit in hits] == [("SNARE", 110)]


def test_oaf_decoder_is_checkpoint_pinned_and_complete(tmp_path):
    runner = _runner_module("drumscribe_oaf_runner.py", "drumscribe_oaf_runner_test")
    class_names = {instrument.value for instrument in runner.TRAINING_CLASSES}
    decoder = tmp_path / "decoder.json"
    decoder.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "modelVersion": "calibrated-v1",
                "checkpointSha256": "expected",
                "thresholds": dict.fromkeys(class_names, 0.5),
                "peakDistances": dict.fromkeys(class_names, 3),
                "onsetShiftFrames": dict.fromkeys(class_names, 0),
                "onsetOffsetSeconds": dict.fromkeys(class_names, 0.001),
            }
        ),
        encoding="utf-8",
    )

    loaded = runner._load_decoder(
        decoder,
        checkpoint_sha256="expected",
        checkpoint_state={"configuration": {"model_version": "base"}},
    )
    assert loaded[3] == dict.fromkeys(class_names, 0.001)
    assert loaded[4] == "calibrated-v1"

    with pytest.raises(ValueError, match="different checkpoint"):
        runner._load_decoder(
            decoder,
            checkpoint_sha256="wrong",
            checkpoint_state={"configuration": {"model_version": "base"}},
        )


def test_hybrid_model_card_is_pinned_to_passing_holdout() -> None:
    repository = Path(__file__).resolve().parents[2]
    card = json.loads(
        (repository / "ml/models/drumscribe-hybrid-v1.json").read_text(encoding="utf-8")
    )
    result_path = (
        repository / "output/supported-kit-hybrid-holdout-v1-2026-09-02/benchmark-result.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert _sha256(result_path) == card["freshHoldout"]["resultSha256"]
    assert (
        result["aggregate"]["20ms"]["family6"]["micro"]["f1"]
        == card["freshHoldout"]["family6MicroF1At20ms"]
    )
    assert result["comparisonTarget"]["met"] is True
    assert result["benchmark"]["postTestTuning"] is False
    assert card["productionApproved"] is False


def _hit(instrument: str, onset: float) -> dict[str, object]:
    return {
        "instrument": instrument,
        "onsetSeconds": onset,
        "velocity": 100,
        "confidence": 0.5,
    }


def test_adtof_decoder_suppresses_a_regular_tom_only_intro() -> None:
    runner = _runner_module("adtof_runner.py", "adtof_runner_intro_test")
    hits = [_hit("MID_TOM", 0.4 + index * 0.55) for index in range(16)]
    hits.extend(
        [
            _hit("KICK", 9.4),
            _hit("SNARE", 9.7),
            _hit("CLOSED_HIHAT", 9.4),
        ]
    )

    filtered, adjustments = runner.filter_rhythm_inconsistencies(hits)

    assert "suppress-regular-tom-only-intro" in adjustments
    assert all(hit["instrument"] != "MID_TOM" for hit in filtered)
    assert len(filtered) == 3


def test_adtof_decoder_suppresses_slow_swing_kick_hihat_collisions() -> None:
    runner = _runner_module("adtof_runner.py", "adtof_runner_swing_test")
    kicks = [1.25 + index * 1.09 for index in range(9)]
    hits = [_hit("KICK", onset) for onset in kicks]
    hits.extend(_hit("SNARE", onset + 0.54) for onset in kicks)
    hits.extend(_hit("CLOSED_HIHAT", onset) for onset in kicks)
    hits.extend(_hit("CLOSED_HIHAT", onset + 0.54) for onset in kicks)

    filtered, adjustments = runner.filter_rhythm_inconsistencies(hits)

    assert "suppress-slow-swing-kick-hihat-collisions" in adjustments
    remaining_hihats = [
        hit for hit in filtered if hit["instrument"] == "CLOSED_HIHAT"
    ]
    assert len(remaining_hihats) == len(kicks)
    assert all(
        not runner._near_any(float(hit["onsetSeconds"]), kicks, 0.04)
        for hit in remaining_hihats
    )


def test_adtof_decoder_leaves_an_ordinary_rock_pattern_unchanged() -> None:
    runner = _runner_module("adtof_runner.py", "adtof_runner_rock_test")
    kicks = [index * 0.25 for index in range(16)]
    hits = [_hit("KICK", onset) for onset in kicks]
    hits.extend(_hit("CLOSED_HIHAT", onset) for onset in kicks)
    hits.extend(_hit("SNARE", onset + 0.125) for onset in kicks)

    filtered, adjustments = runner.filter_rhythm_inconsistencies(hits)

    assert adjustments == ()
    assert filtered == hits
