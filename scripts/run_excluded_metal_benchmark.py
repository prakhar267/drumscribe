#!/usr/bin/env python3
"""Run a frozen excluded-performance metal benchmark in three sealed phases."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import soundfile as sf
from drumscribe_ml.kit_adapter import KitAdapterModel, transcribe_wav
from drumscribe_music import (
    DefaultQuantizer,
    Instrument,
    RawDrumHit,
    ResearchBeatThisTrackingProvider,
)
from drumscribe_music.exporters import write_midi, write_musicxml, write_pdf
from run_sealed_metal_benchmark import (
    _match_times,
    _metric_payload,
    _notation_rows,
    _score_by_class,
    _separation_metrics,
    _sha256,
    _tempo_payload,
    _write_json_new,
)

SAMPLE_RATE = 44_100
TITLE = "Steel Horizon"
ARTIST = "DrumScribe"


def _master(samples: np.ndarray) -> np.ndarray:
    shaped = np.tanh(samples * 1.08)
    peak = float(np.max(np.abs(shaped)))
    return (shaped * (0.95 / max(0.95, peak))).astype(np.float32)


def _metal_backing(duration: float, bpm: float) -> np.ndarray:
    """Generate deterministic bass and double-tracked distorted guitars."""

    result = np.zeros((math.ceil(duration * SAMPLE_RATE), 2), dtype=np.float32)
    beat_seconds = 60 / bpm
    roots = (41.20, 43.65, 49.00, 36.71, 41.20, 55.00)
    beat_count = math.ceil(duration / beat_seconds)
    for beat in range(beat_count):
        root = roots[(beat // 8) % len(roots)]
        start = round(beat * beat_seconds * SAMPLE_RATE)
        bass_length = round(beat_seconds * 0.90 * SAMPLE_RATE)
        bass_time = np.arange(bass_length) / SAMPLE_RATE
        bass_envelope = np.minimum(1, bass_time * 180) * np.exp(-bass_time * 4.4)
        bass = np.sin(2 * math.pi * root * bass_time) + 0.32 * np.sin(
            4 * math.pi * root * bass_time
        )
        bass = np.tanh(bass * 2.5) * bass_envelope * 0.22
        end = min(len(result), start + bass_length)
        result[start:end] += bass[: end - start, None]

        # Two palm-muted guitar tracks plus an eighth-note chug on alternate beats.
        offsets = (0.0, 0.008, beat_seconds / 2 if beat % 2 else None)
        for index, offset in enumerate(offsets):
            if offset is None:
                continue
            pan = (-0.72, 0.72, -0.18)[index]
            guitar_start = start + round(offset * SAMPLE_RATE)
            if guitar_start >= len(result):
                continue
            guitar_length = round(beat_seconds * 0.46 * SAMPLE_RATE)
            guitar_time = np.arange(guitar_length) / SAMPLE_RATE
            chord = sum(
                np.sin(2 * math.pi * root * ratio * harmonic * guitar_time) / harmonic
                for ratio in (2.0, 3.0)
                for harmonic in (1, 3, 5, 7)
            )
            envelope = np.minimum(1, guitar_time * 260) * np.exp(-guitar_time * 8.2)
            guitar = np.tanh(chord * 1.9) * envelope * 0.12
            guitar_end = min(len(result), guitar_start + guitar_length)
            count = guitar_end - guitar_start
            result[guitar_start:guitar_end, 0] += guitar[:count] * math.sqrt(
                (1 - pan) / 2
            )
            result[guitar_start:guitar_end, 1] += guitar[:count] * math.sqrt(
                (1 + pan) / 2
            )
    return _master(result)


def prepare(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    source = args.source_audio.resolve(strict=True)
    output.mkdir(parents=True)
    audio, sample_rate = sf.read(source, always_2d=True, dtype="float32")
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"expected {SAMPLE_RATE} Hz audio, received {sample_rate}")
    start = round(args.crop_start * sample_rate)
    end = start + round(args.duration * sample_rate)
    drums = audio[start:end]
    if len(drums) != end - start:
        raise ValueError("requested crop exceeds the source audio")
    backing = _metal_backing(args.duration, args.bpm)
    full_mix = _master(0.80 * drums + 0.92 * backing)
    drums_path = output / "reference-drums.wav"
    mix_path = output / "full-mix.wav"
    sf.write(drums_path, drums, sample_rate, subtype="PCM_24")
    sf.write(mix_path, full_mix, sample_rate, subtype="PCM_24")
    _write_json_new(
        output / "sealed-input-manifest.json",
        {
            "schemaVersion": 1,
            "benchmark": "excluded-groove-metal-v2",
            "title": TITLE,
            "sourceAudioSha256": _sha256(source),
            "sourceGroup": args.source_group,
            "cropStartSeconds": args.crop_start,
            "durationSeconds": args.duration,
            "bpmHintUsedForBackingOnly": args.bpm,
            "referenceAnnotationOpened": False,
            "futureModelTrainingExclusion": args.source_group,
            "rightsCleared": True,
            "createdAt": datetime.now(UTC).isoformat(),
            "assets": {
                "fullMixSha256": _sha256(mix_path),
                "referenceDrumsSha256": _sha256(drums_path),
            },
        },
    )
    print(json.dumps({"output": str(output), "fullMix": str(mix_path)}))


def predict(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    prediction = output / "prediction"
    if prediction.exists():
        raise FileExistsError(prediction)
    prediction.mkdir()
    full_mix = args.full_mix.resolve(strict=True)
    drum_stem = args.drum_stem.resolve(strict=True)
    model_path = args.model.resolve(strict=True)
    started = time.perf_counter()
    model = KitAdapterModel.load(model_path)
    predictions = transcribe_wav(drum_stem, model)
    transcription_seconds = time.perf_counter() - started
    raw_hits = [
        RawDrumHit(
            item.instrument,
            onset_seconds=item.onset_seconds,
            velocity=item.velocity,
            confidence=item.confidence,
            metadata={"provider": model.model_version, "frame": item.frame},
        )
        for item in predictions
    ]
    beat_started = time.perf_counter()
    tempo = ResearchBeatThisTrackingProvider().track(full_mix)
    beat_seconds = time.perf_counter() - beat_started
    events = DefaultQuantizer().quantize(raw_hits, tempo)
    payload = {
        "schemaVersion": 1,
        "modelVersion": model.model_version,
        "modelSha256": _sha256(model_path),
        "sourceAudioSha256": _sha256(full_mix),
        "drumStemSha256": _sha256(drum_stem),
        "tempoMap": _tempo_payload(tempo),
        "rawHits": [
            {
                "instrument": hit.instrument_class.value,
                "onsetSeconds": hit.onset_seconds,
                "velocity": hit.velocity,
                "confidence": hit.confidence,
            }
            for hit in raw_hits
        ],
        "events": [event.as_dict() for event in events],
        "timingsSeconds": {
            "transcription": transcription_seconds,
            "beatTracking": beat_seconds,
            "total": time.perf_counter() - started,
        },
    }
    _write_json_new(prediction / "predicted-events.json", payload)
    write_midi(prediction / "predicted.mid", events, tempo)
    write_musicxml(
        prediction / "predicted.musicxml",
        events,
        tempo,
        title=f"{TITLE} - DrumScribe Prediction",
        artist=ARTIST,
    )
    write_pdf(
        prediction / "predicted.pdf",
        events,
        tempo,
        title=f"{TITLE} - DrumScribe Prediction",
        artist=ARTIST,
    )
    print(json.dumps({"prediction": str(prediction), "events": len(events)}))


def _raw_rows(rows: list[dict[str, object]]) -> list[tuple[float, Instrument]]:
    return sorted(
        (
            (float(row["onsetSeconds"]), Instrument(str(row["instrument"])))
            for row in rows
        ),
        key=lambda item: (item[0], item[1].value),
    )


def _report(result: dict[str, object]) -> str:
    metric = result["classAware50ms"]
    onset = result["onsetOnly50ms"]
    notation = result["notationClassAndSlotExact"]
    rows = []
    per_class = result["perClass50ms"]
    reference_counts = result["referenceClassCounts"]
    predicted_counts = result["predictedClassCounts"]
    for instrument in Instrument:
        item = per_class[instrument.value]
        rows.append(
            f"| {instrument.value} | {reference_counts.get(instrument.value, 0)} | "
            f"{predicted_counts.get(instrument.value, 0)} | {item['precision']:.3f} | "
            f"{item['recall']:.3f} | {item['f1']:.3f} |"
        )
    return "\n".join(
        [
            f"# Frozen excluded-performance benchmark: {TITLE}",
            "",
            (
                f"First-run full-pipeline result: **{metric['f1']:.1%} class-aware F1 at "
                f"50 ms**, **{onset['f1']:.1%} onset-only F1**, and "
                f"**{notation['f1']:.1%} exact notation class-and-slot F1**."
            ),
            "",
            "| Class | Reference | Predicted | Precision | Recall | F1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            *rows,
            "",
            "The source performance group was excluded before model training, prediction ran once,",
            "and the annotation was opened only in the score phase. No post-test tuning was done.",
            "",
        ]
    )


def score(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    manifest = json.loads((output / "sealed-input-manifest.json").read_text())
    prediction_path = output / "prediction" / "predicted-events.json"
    prediction = json.loads(prediction_path.read_text())
    annotation = json.loads(args.reference_annotation.resolve(strict=True).read_text())
    crop_start = float(manifest["cropStartSeconds"])
    duration = float(manifest["durationSeconds"])
    reference_hits = [
        RawDrumHit(
            Instrument(str(event["instrument"])),
            onset_seconds=float(event["onsetSeconds"]) - crop_start,
            velocity=max(1, min(127, int(event["velocity"]))),
            confidence=1.0,
            metadata={"provider": "licensed-reference"},
        )
        for event in annotation["events"]
        if crop_start <= float(event["onsetSeconds"]) < crop_start + duration
        and str(event["instrument"]) in {instrument.value for instrument in Instrument}
    ]
    reference_tempo = ResearchBeatThisTrackingProvider().track(
        output / "reference-drums.wav"
    )
    reference_events = DefaultQuantizer().quantize(reference_hits, reference_tempo)
    reference_payload = {
        "schemaVersion": 1,
        "sourceAnnotationSha256": _sha256(args.reference_annotation),
        "tempoMap": _tempo_payload(reference_tempo),
        "rawHits": [
            {
                "instrument": hit.instrument_class.value,
                "onsetSeconds": hit.onset_seconds,
                "velocity": hit.velocity,
                "confidence": 1.0,
            }
            for hit in reference_hits
        ],
        "events": [event.as_dict() for event in reference_events],
    }
    reference_path = output / "reference-events.json"
    _write_json_new(reference_path, reference_payload)
    write_midi(output / "reference.mid", reference_events, reference_tempo)
    write_musicxml(
        output / "reference.musicxml",
        reference_events,
        reference_tempo,
        title=f"{TITLE} - Licensed Reference",
        artist=ARTIST,
    )
    write_pdf(
        output / "reference.pdf",
        reference_events,
        reference_tempo,
        title=f"{TITLE} - Licensed Reference",
        artist=ARTIST,
    )

    reference_rows = _raw_rows(reference_payload["rawHits"])
    predicted_rows = _raw_rows(prediction["rawHits"])
    class_50, per_class = _score_by_class(reference_rows, predicted_rows, 0.050)
    class_20, _ = _score_by_class(reference_rows, predicted_rows, 0.020)
    onset_50 = _match_times(
        [row[0] for row in reference_rows],
        [row[0] for row in predicted_rows],
        0.050,
    )
    reference_notation = _notation_rows(reference_payload["events"])
    predicted_notation = _notation_rows(prediction["events"])
    notation, notation_per_class = _score_by_class(
        reference_notation, predicted_notation, 1e-6
    )
    notation_slot = _match_times(
        [row[0] for row in reference_notation],
        [row[0] for row in predicted_notation],
        1e-6,
    )
    supported = [
        value.f1
        for value in per_class.values()
        if value.true_positive + value.false_negative
    ]
    result = {
        "schemaVersion": 1,
        "benchmark": "excluded-groove-metal-v2",
        "track": TITLE,
        "modelVersion": prediction["modelVersion"],
        "sealedManifestSha256": _sha256(output / "sealed-input-manifest.json"),
        "referenceEventsSha256": _sha256(reference_path),
        "predictionEventsSha256": _sha256(prediction_path),
        "referenceEvents": len(reference_rows),
        "predictedEvents": len(predicted_rows),
        "referenceClassCounts": dict(Counter(item[1].value for item in reference_rows)),
        "predictedClassCounts": dict(Counter(item[1].value for item in predicted_rows)),
        "classAware50ms": _metric_payload(class_50),
        "classAware20ms": _metric_payload(class_20),
        "onsetOnly50ms": _metric_payload(onset_50),
        "supportedMacroF1At50ms": statistics.fmean(supported),
        "perClass50ms": {
            instrument.value: _metric_payload(per_class[instrument])
            for instrument in Instrument
        },
        "notationClassAndSlotExact": _metric_payload(notation),
        "notationSlotOnlyExact": _metric_payload(notation_slot),
        "notationPerClassExact": {
            instrument.value: _metric_payload(notation_per_class[instrument])
            for instrument in Instrument
        },
        "tempo": {
            "referenceFirstBpm": reference_payload["tempoMap"]["changes"][0]["bpm"],
            "estimatedFirstBpm": prediction["tempoMap"]["changes"][0]["bpm"],
        },
        "separation": _separation_metrics(
            output / "reference-drums.wav", args.drum_stem.resolve(strict=True)
        ),
        "timingsSeconds": prediction["timingsSeconds"],
        "testProtocol": {
            "sourceGroupExcludedBeforeTraining": manifest["sourceGroup"],
            "referenceNotAvailableToPrediction": True,
            "predictionRunCount": 1,
            "postTestTuning": False,
            "rightsCleared": True,
        },
    }
    _write_json_new(output / "benchmark-result.json", result)
    (output / "BENCHMARK_REPORT.md").write_text(_report(result), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subcommands.add_parser("prepare")
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--source-audio", type=Path, required=True)
    prepare_parser.add_argument("--source-group", required=True)
    prepare_parser.add_argument("--crop-start", type=float, default=45.0)
    prepare_parser.add_argument("--duration", type=float, default=35.0)
    prepare_parser.add_argument("--bpm", type=float, default=136.0)
    predict_parser = subcommands.add_parser("predict")
    predict_parser.add_argument("--output", type=Path, required=True)
    predict_parser.add_argument("--full-mix", type=Path, required=True)
    predict_parser.add_argument("--drum-stem", type=Path, required=True)
    predict_parser.add_argument("--model", type=Path, required=True)
    score_parser = subcommands.add_parser("score")
    score_parser.add_argument("--output", type=Path, required=True)
    score_parser.add_argument("--reference-annotation", type=Path, required=True)
    score_parser.add_argument("--drum-stem", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    elif args.command == "predict":
        predict(args)
    else:
        score(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
