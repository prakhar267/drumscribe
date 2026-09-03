#!/usr/bin/env python3
"""Score frozen drum predictions on the real-performance MDB Drums split.

MDB Drums is CC BY-NC-SA 4.0 and is therefore used only for local research
evaluation.  The script never trains on, calibrates against, or redistributes
the MIREX test split.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from drumscribe_music import RawDrumHit, RhythmCompletionSettings, complete_rhythm
from drumscribe_music.providers.research import ResearchBeatThisTrackingProvider
from model_runners._midi_contract import GM_DRUM_CLASSES

TRAIN_TRACKS = (
    "MusicDelta_80sRock",
    "MusicDelta_BebopJazz",
    "MusicDelta_Britpop",
    "MusicDelta_CoolJazz",
    "MusicDelta_Disco",
    "MusicDelta_FunkJazz",
    "MusicDelta_FusionJazz",
    "MusicDelta_Reggae",
    "MusicDelta_Rock",
    "MusicDelta_Rockabilly",
    "MusicDelta_Shadows",
    "MusicDelta_Zeppelin",
)
TEST_TRACKS = (
    "MusicDelta_Beatles",
    "MusicDelta_Country1",
    "MusicDelta_FreeJazz",
    "MusicDelta_Gospel",
    "MusicDelta_Grunge",
    "MusicDelta_Hendrix",
    "MusicDelta_LatinJazz",
    "MusicDelta_ModalJazz",
    "MusicDelta_Punk",
    "MusicDelta_SpeedMetal",
    "MusicDelta_SwingJazz",
)
MDB_TO_FAMILY = {
    "KD": "KICK",
    "SD": "SNARE",
    "HH": "HIHAT",
    "TT": "TOM",
    "CY": "CYMBAL",
    "OT": "OTHER",
}
INSTRUMENT_TO_FAMILY = {
    "KICK": "KICK",
    "SNARE": "SNARE",
    "CROSS_STICK": "SNARE",
    "CLOSED_HIHAT": "HIHAT",
    "OPEN_HIHAT": "HIHAT",
    "PEDAL_HIHAT": "HIHAT",
    "RIDE": "CYMBAL",
    "RIDE_BELL": "CYMBAL",
    "CRASH": "CYMBAL",
    "HIGH_TOM": "TOM",
    "MID_TOM": "TOM",
    "LOW_TOM": "TOM",
    "FLOOR_TOM": "TOM",
    "TAMBOURINE": "OTHER",
}
# MDB's six-class protocol groups side-stick and tambourine under "other".
# Keep this adapter separate from the product's own snare-family semantics.
MDB_INSTRUMENT_TO_FAMILY = {
    **INSTRUMENT_TO_FAMILY,
    "CROSS_STICK": "OTHER",
}
FAMILY_TO_INSTRUMENT = {
    "KICK": "KICK",
    "SNARE": "SNARE",
    "HIHAT": "CLOSED_HIHAT",
    "TOM": "MID_TOM",
    "CYMBAL": "CRASH",
}

Event = tuple[float, str]


def _match_times(
    references: list[float], predictions: list[float], tolerance: float
) -> tuple[int, int, int, list[float]]:
    refs = sorted(references)
    preds = sorted(predictions)
    ref_index = pred_index = true_positive = false_positive = false_negative = 0
    errors: list[float] = []
    while ref_index < len(refs) and pred_index < len(preds):
        reference = refs[ref_index]
        prediction = preds[pred_index]
        if prediction < reference - tolerance:
            false_positive += 1
            pred_index += 1
        elif reference < prediction - tolerance:
            false_negative += 1
            ref_index += 1
        else:
            true_positive += 1
            errors.append(abs(prediction - reference))
            ref_index += 1
            pred_index += 1
    return (
        true_positive,
        false_positive + len(preds) - pred_index,
        false_negative + len(refs) - ref_index,
        errors,
    )


def _metrics(
    true_positive: int, false_positive: int, false_negative: int
) -> dict[str, Any]:
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    denominator = 2 * true_positive + false_positive + false_negative
    f1 = 2 * true_positive / denominator if denominator else 0.0
    return {
        "tp": true_positive,
        "fp": false_positive,
        "fn": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def score(
    reference: list[Event], prediction: list[Event], tolerance: float
) -> dict[str, Any]:
    labels = sorted(
        {label for _, label in reference} | {label for _, label in prediction}
    )
    totals = [0, 0, 0]
    timing_errors: list[float] = []
    supported_f1: list[float] = []
    per_class: dict[str, Any] = {}
    for label in labels:
        matched = _match_times(
            [time for time, item in reference if item == label],
            [time for time, item in prediction if item == label],
            tolerance,
        )
        metrics = _metrics(*matched[:3])
        support = sum(item == label for _, item in reference)
        metrics["support"] = support
        if matched[3]:
            metrics["meanAbsoluteTimingErrorMs"] = statistics.fmean(matched[3]) * 1000
        per_class[label] = metrics
        for index in range(3):
            totals[index] += matched[index]
        timing_errors.extend(matched[3])
        if support:
            supported_f1.append(float(metrics["f1"]))
    result = {
        "micro": _metrics(*totals),
        "supportedMacroF1": (statistics.fmean(supported_f1) if supported_f1 else 0.0),
        "referenceEvents": len(reference),
        "predictedEvents": len(prediction),
        "perClass": per_class,
    }
    if timing_errors:
        result["meanAbsoluteTimingErrorMs"] = statistics.fmean(timing_errors) * 1000
    return result


def _combine_event_lists(
    items: list[list[Event]], stride: float = 100.0
) -> list[Event]:
    return [
        (time + index * stride, instrument)
        for index, events in enumerate(items)
        for time, instrument in events
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reference_events(path: Path) -> list[Event]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        onset, label = line.split()[:2]
        events.append((float(onset), MDB_TO_FAMILY[label]))
    return sorted(events)


def _midi_events(path: Path) -> list[Event]:
    try:
        import mido
    except ImportError as exc:  # pragma: no cover - environment contract
        raise RuntimeError("mido is required to evaluate MIDI predictions") from exc
    elapsed = 0.0
    events: list[Event] = []
    for message in mido.MidiFile(path):
        elapsed += float(message.time)
        if message.type != "note_on" or int(message.velocity) <= 0:
            continue
        if int(getattr(message, "channel", -1)) != 9:
            continue
        instrument = GM_DRUM_CLASSES.get(int(message.note))
        family = INSTRUMENT_TO_FAMILY.get(instrument or "")
        if family:
            events.append((elapsed, family))
    return sorted(events)


def _drumscribe_json_events(path: Path) -> list[Event]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    events: list[Event] = []
    for hit in payload.get("hits", []):
        family = MDB_INSTRUMENT_TO_FAMILY.get(str(hit.get("instrument", "")))
        if family:
            events.append((float(hit["onsetSeconds"]), family))
    return sorted(events)


def _complete_events(
    events: list[Event],
    *,
    full_mix: Path,
    beat_tracker: ResearchBeatThisTrackingProvider,
    settings: RhythmCompletionSettings,
) -> tuple[list[Event], dict[str, Any]]:
    result = complete_rhythm(
        (
            RawDrumHit(FAMILY_TO_INSTRUMENT[family], onset, confidence=0.5)
            for onset, family in events
            if family in FAMILY_TO_INSTRUMENT
        ),
        beat_tracker.track(full_mix),
        settings=settings,
    )
    completed = [
        (hit.onset_seconds, INSTRUMENT_TO_FAMILY[str(hit.instrument_class)])
        for hit in result.hits
    ]
    return sorted(completed), {"applied": result.applied, **dict(result.metadata)}


def _aggregate_scores(items: list[dict[str, Any]]) -> dict[str, Any]:
    references = _combine_event_lists([item["reference"] for item in items])
    predictions = _combine_event_lists([item["prediction"] for item in items])
    return {
        f"{milliseconds}ms": score(references, predictions, milliseconds / 1000)
        for milliseconds in (20, 50, 100)
    }


def evaluate(args: argparse.Namespace) -> None:
    dataset = args.dataset.resolve(strict=True)
    predictions = args.predictions.resolve(strict=True)
    tracks = TRAIN_TRACKS if args.split == "train" else TEST_TRACKS
    annotation_root = dataset / "annotations" / "class"
    full_mix_root = dataset / "audio" / "full_mix"
    beat_tracker = (
        ResearchBeatThisTrackingProvider(device=args.beat_device)
        if args.rhythm_completion
        else None
    )
    completion_settings = RhythmCompletionSettings(
        minimum_anchor_confidence=args.minimum_anchor_confidence
    )
    scored: list[dict[str, Any]] = []
    artifact_rows = []
    for track in tracks:
        reference_path = annotation_root / f"{track}_class.txt"
        prediction_path = predictions / f"{track}{args.prediction_suffix}"
        reference = _reference_events(reference_path)
        prediction = (
            _midi_events(prediction_path)
            if args.prediction_format == "midi"
            else _drumscribe_json_events(prediction_path)
        )
        completion: dict[str, Any] | None = None
        if beat_tracker is not None:
            prediction, completion = _complete_events(
                prediction,
                full_mix=full_mix_root / f"{track}_MIX.wav",
                beat_tracker=beat_tracker,
                settings=completion_settings,
            )
        scores = {
            f"{milliseconds}ms": score(reference, prediction, milliseconds / 1000)
            for milliseconds in (20, 50, 100)
        }
        scored.append(
            {
                "track": track,
                "reference": reference,
                "prediction": prediction,
                "scores": scores,
            }
        )
        artifact_rows.append(
            {
                "track": track,
                "referenceEvents": len(reference),
                "predictedEvents": len(prediction),
                "referenceClassCounts": dict(Counter(label for _, label in reference)),
                "predictionClassCounts": dict(
                    Counter(label for _, label in prediction)
                ),
                "scores": scores,
                "rhythmCompletion": completion,
                "hashes": {
                    "reference": _sha256(reference_path),
                    "prediction": _sha256(prediction_path),
                },
            }
        )
        print(
            json.dumps(
                {
                    "track": track,
                    "f1At50ms": scores["50ms"]["micro"]["f1"],
                    "events": len(prediction),
                }
            ),
            flush=True,
        )
    payload = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "MDB Drums real-performance MIREX split",
            "split": args.split,
            "trackCount": len(tracks),
            "datasetLicense": "CC BY-NC-SA 4.0",
            "researchOnly": True,
            "predictionSource": args.prediction_source,
            "rhythmCompletion": args.rhythm_completion,
            "testReferencesUsedForTrainingOrCalibration": False,
        },
        "aggregate": _aggregate_scores(scored),
        "tracks": artifact_rows,
    }
    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": str(destination), "aggregate": payload["aggregate"]}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/research-corpus/MDBDrums/MDB Drums"),
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--prediction-suffix", default="_adtof-pt.mid")
    parser.add_argument(
        "--prediction-format",
        choices=("midi", "drumscribe-json"),
        default="midi",
    )
    parser.add_argument("--prediction-source", required=True)
    parser.add_argument("--split", choices=("train", "test"), required=True)
    parser.add_argument("--rhythm-completion", action="store_true")
    parser.add_argument(
        "--minimum-anchor-confidence",
        type=float,
        default=0.75,
        help=(
            "minimum kick confidence for grid fitting; lower only for research "
            "adapters whose output contract lacks calibrated probabilities"
        ),
    )
    parser.add_argument("--beat-device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--output", type=Path, required=True)
    evaluate(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
