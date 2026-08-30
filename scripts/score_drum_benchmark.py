"""Score DrumScribe event and source-separation output against MDB Drums."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

MDB_CLASS = {
    "KICK": "KD",
    "SNARE": "SD",
    "CROSS_STICK": "OT",
    "CLOSED_HIHAT": "HH",
    "OPEN_HIHAT": "HH",
    "PEDAL_HIHAT": "HH",
    "RIDE": "CY",
    "RIDE_BELL": "CY",
    "CRASH": "CY",
    "HIGH_TOM": "TT",
    "MID_TOM": "TT",
    "LOW_TOM": "TT",
    "FLOOR_TOM": "TT",
}
CLASS_ORDER = ("KD", "SD", "HH", "TT", "CY", "OT")


@dataclass(frozen=True)
class Event:
    onset: float
    instrument: str


@dataclass(frozen=True)
class MatchResult:
    true_positive: int
    false_positive: int
    false_negative: int
    errors: tuple[float, ...]

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0


def parse_reference(path: Path) -> list[Event]:
    events: list[Event] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        onset, instrument = line.split()[:2]
        events.append(Event(float(onset), instrument))
    return sorted(events, key=lambda event: (event.onset, event.instrument))


def parse_prediction(path: Path) -> tuple[dict[str, Any], list[Event], list[Event]]:
    payload = json.loads(path.read_text())
    project = dict(payload["project"])
    project["bpm"] = payload["events"]["tempoBpm"]
    project["beatsPerMeasure"] = payload["events"]["timeSignatureNumerator"]
    events = [
        Event(float(item["onsetSeconds"]), MDB_CLASS[str(item["instrument"])])
        for item in payload["events"]["items"]
    ]
    notation_events = [
        Event(
            float(item["measureIndex"]) * project["beatsPerMeasure"]
            + float(item["beatPosition"]),
            MDB_CLASS[str(item["instrument"])],
        )
        for item in payload["events"]["items"]
    ]
    return (
        project,
        sorted(events, key=lambda event: (event.onset, event.instrument)),
        sorted(notation_events, key=lambda event: (event.onset, event.instrument)),
    )


def match_times(
    reference: list[float], prediction: list[float], tolerance: float
) -> MatchResult:
    reference = sorted(reference)
    prediction = sorted(prediction)
    ref_index = 0
    pred_index = 0
    errors: list[float] = []
    false_positive = 0
    false_negative = 0
    while ref_index < len(reference) and pred_index < len(prediction):
        delta = prediction[pred_index] - reference[ref_index]
        if delta < -tolerance:
            false_positive += 1
            pred_index += 1
        elif delta > tolerance:
            false_negative += 1
            ref_index += 1
        else:
            errors.append(abs(delta))
            ref_index += 1
            pred_index += 1
    false_negative += len(reference) - ref_index
    false_positive += len(prediction) - pred_index
    return MatchResult(len(errors), false_positive, false_negative, tuple(errors))


def score_by_class(
    reference: list[Event], prediction: list[Event], tolerance: float
) -> tuple[MatchResult, dict[str, MatchResult]]:
    results: dict[str, MatchResult] = {}
    for instrument in CLASS_ORDER:
        results[instrument] = match_times(
            [event.onset for event in reference if event.instrument == instrument],
            [event.onset for event in prediction if event.instrument == instrument],
            tolerance,
        )
    return combine(results.values()), results


def combine(results) -> MatchResult:
    values = tuple(results)
    return MatchResult(
        sum(item.true_positive for item in values),
        sum(item.false_positive for item in values),
        sum(item.false_negative for item in values),
        tuple(error for item in values for error in item.errors),
    )


def load_mono(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, always_2d=True, dtype="float64")
    return np.mean(audio, axis=1), sample_rate


def separation_metrics(reference_path: Path, prediction_path: Path) -> dict[str, float]:
    reference, reference_rate = load_mono(reference_path)
    prediction, prediction_rate = load_mono(prediction_path)
    if reference_rate != prediction_rate:
        raise ValueError(
            f"sample rates differ: reference={reference_rate}, prediction={prediction_rate}"
        )
    sample_count = min(len(reference), len(prediction))
    reference = reference[:sample_count]
    prediction = prediction[:sample_count]
    reference -= np.mean(reference)
    prediction -= np.mean(prediction)
    scale = float(
        np.dot(prediction, reference) / (np.dot(reference, reference) + 1e-12)
    )
    target = scale * reference
    noise = prediction - target
    si_sdr = 10 * math.log10(
        (float(np.dot(target, target)) + 1e-12) / (float(np.dot(noise, noise)) + 1e-12)
    )
    correlation = float(np.corrcoef(reference, prediction)[0, 1])
    return {
        "sampleRate": reference_rate,
        "comparedSeconds": sample_count / reference_rate,
        "siSdrDb": si_sdr,
        "correlation": correlation,
    }


def parse_beats(path: Path) -> list[float]:
    return [
        float(line.split()[0]) for line in path.read_text().splitlines() if line.strip()
    ]


def reference_bpm(beats: list[float]) -> float:
    return 60 / statistics.median(second - first for first, second in pairwise(beats))


def beat_coordinate(onset: float, beats: list[float]) -> float:
    if len(beats) < 2:
        raise ValueError("at least two reference beats are required")
    if onset <= beats[0]:
        return (onset - beats[0]) / (beats[1] - beats[0])
    for index, (first, second) in enumerate(pairwise(beats)):
        if onset <= second:
            return index + (onset - first) / (second - first)
    return len(beats) - 1 + (onset - beats[-1]) / (beats[-1] - beats[-2])


def reference_notation(events: list[Event], beats: list[float]) -> list[Event]:
    return sorted(
        (
            Event(round(beat_coordinate(event.onset, beats) * 4) / 4, event.instrument)
            for event in events
        ),
        key=lambda event: (event.onset, event.instrument),
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def result_payload(args: argparse.Namespace) -> dict[str, Any]:
    reference = parse_reference(args.reference_events)
    project, prediction, prediction_notation = parse_prediction(args.predicted_events)
    beats = parse_beats(args.reference_beats)
    expected_notation = reference_notation(reference, beats)
    class_50, per_class = score_by_class(reference, prediction, 0.050)
    class_20, _ = score_by_class(reference, prediction, 0.020)
    onset_50 = match_times(
        [event.onset for event in reference],
        [event.onset for event in prediction],
        0.050,
    )
    notation_class, notation_per_class = score_by_class(
        expected_notation, prediction_notation, 1e-6
    )
    notation_slot = match_times(
        [event.onset for event in expected_notation],
        [event.onset for event in prediction_notation],
        1e-6,
    )
    separation = separation_metrics(args.reference_drums, args.predicted_drums)
    ref_bpm = reference_bpm(beats)
    generated_bpm = float(project["bpm"])
    return {
        "track": "MusicDelta_Beatles",
        "referenceEvents": len(reference),
        "predictedEvents": len(prediction),
        "referenceClassCounts": dict(Counter(event.instrument for event in reference)),
        "predictedClassCounts": dict(Counter(event.instrument for event in prediction)),
        "classAware50ms": metric_payload(class_50),
        "classAware20ms": metric_payload(class_20),
        "onsetOnly50ms": metric_payload(onset_50),
        "perClass50ms": {name: metric_payload(per_class[name]) for name in CLASS_ORDER},
        "notationClassAndSlotExact": metric_payload(notation_class),
        "notationSlotOnlyExact": metric_payload(notation_slot),
        "notationPerClassExact": {
            name: metric_payload(notation_per_class[name]) for name in CLASS_ORDER
        },
        "tempo": {
            "referenceBpm": ref_bpm,
            "generatedBpm": generated_bpm,
            "absoluteErrorBpm": abs(generated_bpm - ref_bpm),
        },
        "separation": separation,
        "exactRawEventMatch": reference == prediction,
        "exactNotationMatch": expected_notation == prediction_notation,
        "artifacts": {
            "referenceEventsSha256": sha256(args.reference_events),
            "referenceDrumsSha256": sha256(args.reference_drums),
            "predictedEventsSha256": sha256(args.predicted_events),
            "predictedDrumsSha256": sha256(args.predicted_drums),
        },
    }


def metric_payload(result: MatchResult) -> dict[str, Any]:
    return {
        "truePositive": result.true_positive,
        "falsePositive": result.false_positive,
        "falseNegative": result.false_negative,
        "precision": result.precision,
        "recall": result.recall,
        "f1": result.f1,
        "meanAbsoluteTimingErrorMs": (
            statistics.fmean(result.errors) * 1000 if result.errors else None
        ),
    }


def markdown(payload: dict[str, Any]) -> str:
    main = payload["classAware50ms"]
    onset = payload["onsetOnly50ms"]
    notation = payload["notationClassAndSlotExact"]
    notation_slot = payload["notationSlotOnlyExact"]
    tempo = payload["tempo"]
    separation = payload["separation"]
    rows = []
    for instrument, item in payload["perClass50ms"].items():
        rows.append(
            f"| {instrument} | {item['truePositive']} | {item['falsePositive']} | "
            f"{item['falseNegative']} | {item['precision']:.3f} | {item['recall']:.3f} | "
            f"{item['f1']:.3f} |"
        )
    return "\n".join(
        [
            "# MDB Drums benchmark: MusicDelta_Beatles",
            "",
            (
                "Exact reference-notation match: "
                f"**{'yes' if payload['exactNotationMatch'] else 'no'}**."
            ),
            "",
            "## Summary",
            "",
            f"- Reference events: {payload['referenceEvents']}",
            f"- DrumScribe events: {payload['predictedEvents']}",
            (
                f"- Class-aware 50 ms precision / recall / F1: "
                f"{main['precision']:.3f} / {main['recall']:.3f} / {main['f1']:.3f}"
            ),
            (
                f"- Onset-only 50 ms precision / recall / F1: "
                f"{onset['precision']:.3f} / {onset['recall']:.3f} / {onset['f1']:.3f}"
            ),
            (
                f"- Exact notated class+slot precision / recall / F1: "
                f"{notation['precision']:.3f} / {notation['recall']:.3f} / "
                f"{notation['f1']:.3f}"
            ),
            (
                f"- Exact notated slot-only precision / recall / F1: "
                f"{notation_slot['precision']:.3f} / {notation_slot['recall']:.3f} / "
                f"{notation_slot['f1']:.3f}"
            ),
            (
                f"- Reference / generated tempo: {tempo['referenceBpm']:.2f} / "
                f"{tempo['generatedBpm']:.2f} BPM"
            ),
            (
                f"- Isolated-stem SI-SDR / waveform correlation: "
                f"{separation['siSdrDb']:.2f} dB / {separation['correlation']:.3f}"
            ),
            "",
            "## Class-aware results at 50 ms",
            "",
            "| Class | TP | FP | FN | Precision | Recall | F1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            *rows,
            "",
            "MDB classes: KD kick, SD snare, HH hi-hat, TT toms, CY cymbals, OT other percussion.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-events", type=Path, required=True)
    parser.add_argument("--reference-beats", type=Path, required=True)
    parser.add_argument("--reference-drums", type=Path, required=True)
    parser.add_argument("--predicted-events", type=Path, required=True)
    parser.add_argument("--predicted-drums", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    payload = result_payload(args)
    args.json_output.write_text(json.dumps(payload, indent=2) + "\n")
    args.markdown_output.write_text(markdown(payload))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
