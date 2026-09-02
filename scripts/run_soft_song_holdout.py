#!/usr/bin/env python3
"""Generate, predict, and score one sealed original soft-song holdout."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf
from drumscribe_music import Instrument, TempoMap
from drumscribe_music.exporters import write_midi, write_musicxml, write_pdf
from model_runners.drumscribe_hybrid_runner import transcribe
from run_competitive_drum_benchmark import score_taxonomies
from run_hard_metal_market_benchmark import (
    KIT_PATH,
    OFFSET_SECONDS,
    SAMPLE_RATE,
    WINDOW_SECONDS,
    _asset,
    _event,
    _master,
    _render_drums,
    _sha256,
    _tempo_payload,
    _write_json_new,
)

SLUG = "quiet-horizon-soft-ballad"
TITLE = "Quiet Horizon"
BPM = 84.0
BARS = 7
SEED = 920_284


def _soft_events() -> tuple[TempoMap, list[object]]:
    tempo = TempoMap.constant(BPM, offset_seconds=OFFSET_SECONDS)
    event_map: dict[tuple[Fraction, Instrument], object] = {}

    def add(step: int, instrument: Instrument, velocity: int) -> None:
        beat = Fraction(step, 4)
        event_map[(beat, instrument)] = _event(tempo, beat, instrument, velocity)

    for measure in range(BARS):
        start = measure * 16
        kicks = (0, 8) if measure % 2 == 0 else (0, 6, 10)
        if measure == BARS - 1:
            kicks = (0, 8, 14)
        for position in kicks:
            add(start + position, Instrument.KICK, 72 if position == 0 else 64)
        for position in (4, 12):
            add(start + position, Instrument.SNARE, 68 if position == 4 else 73)

        cymbal = Instrument.RIDE if measure in {4, 5} else Instrument.CLOSED_HIHAT
        for position in range(0, 16, 2):
            instrument = cymbal
            if (
                cymbal is Instrument.CLOSED_HIHAT
                and position == 14
                and measure in {2, 6}
            ):
                instrument = Instrument.OPEN_HIHAT
            add(start + position, instrument, 48 + 7 * (position % 4 == 0))

        if measure in {0, 4}:
            add(start, Instrument.CRASH, 78)
        if measure == 3:
            add(start + 12, Instrument.CROSS_STICK, 58)
        if measure == BARS - 1:
            for position, instrument in zip(
                (12, 13, 14, 15),
                (
                    Instrument.HIGH_TOM,
                    Instrument.MID_TOM,
                    Instrument.LOW_TOM,
                    Instrument.FLOOR_TOM,
                ),
                strict=True,
            ):
                add(start + position, instrument, 65 + (position - 12) * 3)

    events = sorted(
        event_map.values(),
        key=lambda event: (event.onset_seconds, event.instrument.value),
    )
    return tempo, events


def _soft_backing(tempo: TempoMap, duration: float) -> np.ndarray:
    output = np.zeros((math.ceil(duration * SAMPLE_RATE), 2), dtype=np.float32)
    chord_roots = (130.81, 110.00, 87.31, 98.00)
    chord_ratios = (1.0, 1.2599, 1.4983)
    measure_seconds = 4 * 60 / BPM
    for measure in range(BARS):
        root = chord_roots[measure % len(chord_roots)]
        start = round(tempo.beat_to_seconds(measure * 4) * SAMPLE_RATE)
        length = round(min(measure_seconds * 0.98, duration) * SAMPLE_RATE)
        axis = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        attack = np.minimum(1.0, axis * 5.0)
        release = np.minimum(1.0, np.maximum(0.0, (length / SAMPLE_RATE - axis) * 2.5))
        envelope = attack * release
        chord = sum(
            np.sin(2 * math.pi * root * ratio * axis)
            + 0.18 * np.sin(4 * math.pi * root * ratio * axis)
            for ratio in chord_ratios
        )
        shimmer = 0.12 * np.sin(2 * math.pi * root * 4 * axis)
        pad = (chord * 0.045 + shimmer * 0.03) * envelope
        end = min(len(output), start + length)
        if end > start:
            count = end - start
            output[start:end, 0] += pad[:count] * 0.92
            output[start:end, 1] += pad[:count] * 1.08

        for beat in range(4):
            note_start = round(tempo.beat_to_seconds(measure * 4 + beat) * SAMPLE_RATE)
            note_length = round(60 / BPM * 0.8 * SAMPLE_RATE)
            note_axis = np.arange(note_length, dtype=np.float32) / SAMPLE_RATE
            bass = np.sin(2 * math.pi * root / 2 * note_axis) + 0.2 * np.sin(
                2 * math.pi * root * note_axis
            )
            bass *= np.minimum(1.0, note_axis * 18) * np.exp(-note_axis * 2.7) * 0.11
            note_end = min(len(output), note_start + note_length)
            if note_end > note_start:
                output[note_start:note_end] += bass[: note_end - note_start, None]
    return _master(output)


def generate(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    kit = args.kit.resolve(strict=True)
    tempo, events = _soft_events()
    duration = min(WINDOW_SECONDS, tempo.beat_to_seconds(BARS * 4) + 0.5)
    clipped = [event for event in events if event.onset_seconds < duration]
    drums = _render_drums(clipped, kit, duration, SEED)
    backing = _soft_backing(tempo, duration)
    full_mix = _master(0.52 * drums + 0.82 * backing)
    audio_path = output / f"{SLUG}.wav"
    drum_path = output / "reference-drums.wav"
    reference_path = output / "reference-events.json"
    sf.write(audio_path, full_mix, SAMPLE_RATE, subtype="PCM_24")
    sf.write(drum_path, drums, SAMPLE_RATE, subtype="PCM_24")
    _write_json_new(
        reference_path,
        {
            "schemaVersion": 1,
            "title": TITLE,
            "style": "soft-pop-ballad",
            "tempoMap": _tempo_payload(tempo),
            "events": [event.as_dict() for event in clipped],
        },
    )
    write_midi(output / "reference.mid", clipped, tempo)
    write_musicxml(
        output / "reference.musicxml", clipped, tempo, title=TITLE, artist="DrumScribe"
    )
    write_pdf(
        output / "reference.pdf", clipped, tempo, title=TITLE, artist="DrumScribe"
    )
    _write_json_new(
        output / "suite-manifest.json",
        {
            "schemaVersion": 1,
            "suite": "soft-song-holdout-v1",
            "sealedAt": datetime.now(UTC).isoformat(),
            "referenceFrozenBeforePrediction": True,
            "rightsCleared": True,
            "compositionRights": "Original deterministic arrangement generated by DrumScribe project code.",
            "drumSamples": {"name": "MuldjordKit FreePats", "license": "CC BY 4.0"},
            "track": {
                "slug": SLUG,
                "title": TITLE,
                "style": "soft-pop-ballad",
                "bpm": BPM,
                "eventCount": len(clipped),
                "classCounts": dict(
                    Counter(event.instrument.value for event in clipped)
                ),
                "assets": {
                    name: _asset(output / name)
                    for name in (
                        f"{SLUG}.wav",
                        "reference-drums.wav",
                        "reference-events.json",
                        "reference.mid",
                        "reference.musicxml",
                        "reference.pdf",
                    )
                },
            },
        },
    )
    print(json.dumps({"generated": SLUG, "seconds": duration, "events": len(clipped)}))


def predict(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    repository = args.repository.resolve(strict=True)
    prediction_path = output / "hybrid-prediction.json"
    if prediction_path.exists():
        raise FileExistsError(prediction_path)
    stem = args.drum_stem.resolve(strict=True)
    payload = transcribe(
        source=stem,
        repository=repository,
        ensemble_config=(
            repository / "ml/configs/groove-stacked-articulation-v16.json"
        ).resolve(strict=True),
        oaf_checkpoint=(repository / "ml/models/supported-kit-oaf-v24.pt").resolve(
            strict=True
        ),
        oaf_decoder=(
            repository / "ml/models/supported-kit-oaf-v24-demucs-subframe-decoder.json"
        ).resolve(strict=True),
        device=args.device,
    )
    _write_json_new(prediction_path, payload)
    _write_json_new(
        output / "prediction-manifest.json",
        {
            "schemaVersion": 1,
            "createdAt": datetime.now(UTC).isoformat(),
            "referenceFilesRead": False,
            "modelPolicyChangedAfterPreviousHoldout": False,
            "predictionSha256": _sha256(prediction_path),
            "drumStemSha256": _sha256(stem),
        },
    )
    print(json.dumps({"predicted": SLUG, "events": len(payload["hits"])}))


def score(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    destination = output / "benchmark-result.json"
    if destination.exists():
        raise FileExistsError(destination)
    reference_payload = json.loads(
        (output / "reference-events.json").read_text(encoding="utf-8")
    )
    prediction_payload = json.loads(
        (output / "hybrid-prediction.json").read_text(encoding="utf-8")
    )
    reference = sorted(
        (float(event["onsetSeconds"]), str(event["instrument"]))
        for event in reference_payload["events"]
        if 0 <= float(event["onsetSeconds"]) < WINDOW_SECONDS
    )
    prediction = sorted(
        (float(hit["onsetSeconds"]), str(hit["instrument"]))
        for hit in prediction_payload["hits"]
        if 0 <= float(hit["onsetSeconds"]) < WINDOW_SECONDS
    )
    scores = {
        f"{milliseconds}ms": score_taxonomies(
            reference, prediction, milliseconds / 1000
        )
        for milliseconds in (20, 50)
    }
    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "Quiet Horizon sealed original soft-pop holdout",
            "status": "sealed_post_freeze_holdout",
            "referenceFrozenBeforePrediction": True,
            "predictionManifestReferenceFilesRead": False,
            "postTestTuning": False,
            "rightsCleared": True,
            "limitations": [
                "This is one original synthetic soft-pop song rendered with the supported MuldjordKit.",
                "One song is a regression probe, not a population estimate for commercial soft music.",
                "Demucs checkpoint licensing remains unresolved for a commercial production launch.",
            ],
        },
        "track": {"slug": SLUG, "title": TITLE, "bpm": BPM},
        "referenceEvents": len(reference),
        "predictedEvents": len(prediction),
        "scores": scores,
        "hashes": {
            "suiteManifest": _sha256(output / "suite-manifest.json"),
            "reference": _sha256(output / "reference-events.json"),
            "prediction": _sha256(output / "hybrid-prediction.json"),
            "predictionManifest": _sha256(output / "prediction-manifest.json"),
        },
    }
    _write_json_new(destination, report)
    print(
        json.dumps(
            {
                "result": str(destination),
                "family6F1At20ms": scores["20ms"]["family6"]["micro"]["f1"],
                "family6F1At50ms": scores["50ms"]["family6"]["micro"]["f1"],
            }
        )
    )


def diagnose(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    prediction_path = args.prediction.resolve(strict=True)
    destination = output / "clean-stem-diagnostic.json"
    if destination.exists():
        raise FileExistsError(destination)
    reference_payload = json.loads(
        (output / "reference-events.json").read_text(encoding="utf-8")
    )
    prediction_payload = json.loads(prediction_path.read_text(encoding="utf-8"))
    reference = sorted(
        (float(event["onsetSeconds"]), str(event["instrument"]))
        for event in reference_payload["events"]
        if 0 <= float(event["onsetSeconds"]) < WINDOW_SECONDS
    )
    prediction = sorted(
        (float(hit["onsetSeconds"]), str(hit["instrument"]))
        for hit in prediction_payload["hits"]
        if 0 <= float(hit["onsetSeconds"]) < WINDOW_SECONDS
    )
    scores = {
        f"{milliseconds}ms": score_taxonomies(
            reference, prediction, milliseconds / 1000
        )
        for milliseconds in (20, 50)
    }
    _write_json_new(
        destination,
        {
            "schemaVersion": 1,
            "createdAt": datetime.now(UTC).isoformat(),
            "kind": "post-score-clean-stem-diagnostic",
            "notPrimaryHoldoutScore": True,
            "performedAfterPrimaryScore": True,
            "modelOrDecoderChanged": False,
            "referenceEvents": len(reference),
            "predictedEvents": len(prediction),
            "scores": scores,
            "hashes": {
                "reference": _sha256(output / "reference-events.json"),
                "prediction": _sha256(prediction_path),
            },
        },
    )
    print(
        json.dumps(
            {
                "diagnostic": str(destination),
                "family6F1At20ms": scores["20ms"]["family6"]["micro"]["f1"],
            }
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    generate_parser = subcommands.add_parser("generate")
    generate_parser.add_argument("--output", type=Path, required=True)
    generate_parser.add_argument("--kit", type=Path, default=KIT_PATH)
    predict_parser = subcommands.add_parser("predict")
    predict_parser.add_argument("--output", type=Path, required=True)
    predict_parser.add_argument("--drum-stem", type=Path, required=True)
    predict_parser.add_argument("--repository", type=Path, default=Path.cwd())
    predict_parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    score_parser = subcommands.add_parser("score")
    score_parser.add_argument("--output", type=Path, required=True)
    diagnose_parser = subcommands.add_parser("diagnose")
    diagnose_parser.add_argument("--output", type=Path, required=True)
    diagnose_parser.add_argument("--prediction", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        generate(args)
    elif args.command == "predict":
        predict(args)
    elif args.command == "score":
        score(args)
    else:
        diagnose(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
