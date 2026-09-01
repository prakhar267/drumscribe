#!/usr/bin/env python3
"""Generate and score a sealed, rights-cleared metal transcription benchmark.

The three explicit phases keep prediction independent of the reference labels:

1. ``generate`` creates a new full mix and exact reference score.
2. ``predict`` accepts only the full mix and an externally isolated drum stem.
3. ``score`` opens the already-frozen prediction and reference artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from drumscribe_ml.ensemble import (
    StackedEnsembleConfig,
    blend_stacked_probabilities,
    decode_stacked_probabilities,
)
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel
from drumscribe_ml.training import TRAINING_CLASSES, TrainingConfig, build_model
from drumscribe_music import (
    DefaultQuantizer,
    DrumEvent,
    EventSource,
    GridSubdivision,
    Instrument,
    RawDrumHit,
    ResearchBeatThisTrackingProvider,
    TempoMap,
)
from drumscribe_music.exporters import write_midi, write_musicxml, write_pdf

SEED = 2_026_090_1
DEFAULT_BARS = 24
DEFAULT_BPM = 180.0
SAMPLE_RATE = 44_100
HOP_LENGTH = 220
MODEL_VERSION = "groove-stacked-articulation-v16"
TOLERANCE_FRAMES = 2

CHECKPOINTS = {
    "c14": "data/licensed-corpus/experiments/groove-oaf-open-cymbal-specialist-v15/checkpoint-0014.pt",
    "e3": "data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v9/checkpoint-0003.pt",
    "e4": "data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v9/checkpoint-0004.pt",
    "s15": "data/licensed-corpus/experiments/groove-oaf-articulation-specialist-v14/checkpoint-0015.pt",
    "v10": "data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v10/best.pt",
    "v12": "data/licensed-corpus/experiments/groove-oaf-family-finetune-v12/best.pt",
    "v7": "data/licensed-corpus/experiments/groove-egmd-spectral-moe-v7/best.pt",
}

SAMPLE_FOLDERS = {
    Instrument.KICK: "KdrumR",
    Instrument.SNARE: "Snare2",
    Instrument.CROSS_STICK: "SnareRest1",
    Instrument.CLOSED_HIHAT: "HihatClosed",
    Instrument.OPEN_HIHAT: "HihatOpen",
    Instrument.PEDAL_HIHAT: "HihatClosed",
    Instrument.RIDE: "RideR",
    Instrument.RIDE_BELL: "RideRBell",
    Instrument.CRASH: "CrashR",
    Instrument.HIGH_TOM: "Tom1",
    Instrument.MID_TOM: "Tom2",
    Instrument.LOW_TOM: "Tom3",
    Instrument.FLOOR_TOM: "Tom4",
}

PAN = {
    Instrument.HIGH_TOM: -0.45,
    Instrument.MID_TOM: -0.15,
    Instrument.LOW_TOM: 0.2,
    Instrument.FLOOR_TOM: 0.48,
    Instrument.RIDE: 0.45,
    Instrument.RIDE_BELL: 0.45,
    Instrument.CRASH: -0.35,
    Instrument.OPEN_HIHAT: -0.5,
    Instrument.CLOSED_HIHAT: -0.5,
    Instrument.PEDAL_HIHAT: -0.5,
    Instrument.TAMBOURINE: 0.58,
}


@dataclass(frozen=True, slots=True)
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


def _event(
    tempo: TempoMap, beat: Fraction, instrument: Instrument, velocity: int
) -> DrumEvent:
    position = tempo.beat_to_position(beat)
    subdivision = {
        1: GridSubdivision.QUARTER,
        2: GridSubdivision.EIGHTH,
        4: GridSubdivision.SIXTEENTH,
        8: GridSubdivision.THIRTY_SECOND,
    }.get(beat.denominator, GridSubdivision.SIXTEENTH)
    return DrumEvent(
        id=f"metal-{beat.numerator}-{beat.denominator}-{instrument.value.lower()}",
        instrument=instrument,
        onset_seconds=tempo.beat_to_seconds(beat),
        velocity=velocity,
        confidence=1.0,
        source=EventSource.SYNTHETIC,
        beat_position=beat,
        measure_index=position.measure_index,
        beat_in_measure=position.beat_in_measure,
        subdivision=subdivision,
        quantized_onset_seconds=tempo.beat_to_seconds(beat),
        created_at=datetime(2000, 1, 1, tzinfo=UTC),
        updated_at=datetime(2000, 1, 1, tzinfo=UTC),
    )


def metal_events(
    *, bars: int = DEFAULT_BARS, bpm: float = DEFAULT_BPM
) -> tuple[TempoMap, list[DrumEvent]]:
    """Create a complete metal arrangement with natural support for all 14 classes."""
    if bars != DEFAULT_BARS:
        raise ValueError(f"sealed fixture requires exactly {DEFAULT_BARS} bars")
    tempo = TempoMap.constant(bpm)
    event_map: dict[tuple[Fraction, Instrument], DrumEvent] = {}

    def add(beat: Fraction, instrument: Instrument, velocity: int) -> None:
        event_map[(beat, instrument)] = _event(tempo, beat, instrument, velocity)

    for measure in range(bars):
        start = Fraction(measure * 4)
        section = measure // 4

        # Double-kick vocabulary changes by section while the backbeat stays legible.
        kick_steps = (
            (0, 2, 4, 6, 8, 10, 12, 14)
            if section in {1, 3, 4}
            else (0, 3, 6, 8, 11, 14)
        )
        if section == 5:
            kick_steps = (0, 1, 4, 5, 8, 9, 12, 13)
        for step in kick_steps:
            add(
                start + Fraction(step, 4), Instrument.KICK, 111 if step % 4 == 0 else 96
            )
        for offset in (Fraction(1), Fraction(3)):
            add(start + offset, Instrument.SNARE, 116)

        if section == 0:
            # Intro: cross-stick pulse and sparse bell/ride statement.
            for step in range(0, 16, 2):
                add(
                    start + Fraction(step, 4),
                    Instrument.CLOSED_HIHAT,
                    78 + 8 * (step % 4 == 0),
                )
            add(start + Fraction(1), Instrument.CROSS_STICK, 88)
            add(start + Fraction(3), Instrument.CROSS_STICK, 92)
            add(start + Fraction(0), Instrument.RIDE_BELL, 108)
        elif section in {1, 2}:
            # Verse: continuous sixteenth hats with deliberate open/pedal articulations.
            for step in range(16):
                beat = start + Fraction(step, 4)
                articulation = Instrument.CLOSED_HIHAT
                if step in {7, 15}:
                    articulation = Instrument.OPEN_HIHAT
                elif step in {5, 13}:
                    articulation = Instrument.PEDAL_HIHAT
                add(beat, articulation, 86 + 10 * (step % 4 == 0))
        elif section in {3, 4}:
            # Chorus: ride eighths, bell accents, pedal hats, crashes, and tambourine.
            for step in range(0, 16, 2):
                beat = start + Fraction(step, 4)
                add(
                    beat,
                    Instrument.RIDE_BELL if step in {0, 8} else Instrument.RIDE,
                    98,
                )
                add(beat + Fraction(1, 4), Instrument.TAMBOURINE, 76)
            for step in (3, 7, 11, 15):
                add(start + Fraction(step, 4), Instrument.PEDAL_HIHAT, 82)
            add(start, Instrument.CRASH, 120)
        else:
            # Breakdown: half-time cymbals and 32nd-note tom fills.
            for step in range(0, 16, 4):
                add(start + Fraction(step, 4), Instrument.RIDE, 94)
            for step in (2, 6, 10, 14):
                add(start + Fraction(step, 4), Instrument.OPEN_HIHAT, 92)
            add(start, Instrument.CRASH, 122)
            fill = (
                Instrument.HIGH_TOM,
                Instrument.MID_TOM,
                Instrument.LOW_TOM,
                Instrument.FLOOR_TOM,
            )
            for step in range(24, 32):
                add(start + Fraction(step, 8), fill[(step - 24) // 2], 105)

        # Short tom turnarounds at each four-bar boundary provide repeated support.
        if measure % 4 == 3:
            for step, instrument in zip(
                (12, 13, 14, 15),
                (
                    Instrument.HIGH_TOM,
                    Instrument.MID_TOM,
                    Instrument.LOW_TOM,
                    Instrument.FLOOR_TOM,
                ),
                strict=True,
            ):
                add(start + Fraction(step, 4), instrument, 110)
        if measure in {0, 4, 8, 12, 16, 20}:
            add(start, Instrument.CRASH, 123)

    return tempo, sorted(
        event_map.values(), key=lambda item: (item.onset_seconds, item.instrument)
    )


def generate_fixture(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError(f"sealed benchmark output already exists: {output}")
    if args.reference_pdf.exists():
        raise FileExistsError(args.reference_pdf)
    kit = args.kit.resolve(strict=True)
    output.mkdir(parents=True)
    tempo, events = metal_events()
    duration = tempo.beat_to_seconds(Fraction(DEFAULT_BARS * 4)) + 2.5
    drums = _render_drums(events, kit, duration=duration)
    instruments = _render_instruments(tempo, duration=duration)
    full_mix = _master(drums * 0.82 + instruments * 0.58)
    sf.write(output / "reference-drums.wav", drums, SAMPLE_RATE, subtype="PCM_16")
    sf.write(output / "sealed-metal-song.wav", full_mix, SAMPLE_RATE, subtype="PCM_16")

    payload = {
        "schemaVersion": 1,
        "title": "Forged in Silence",
        "artist": "DrumScribe",
        "rights": (
            "Original arrangement and synthesized instruments by DrumScribe. Drum one-shots "
            "use MuldjordKit FreePats under CC BY 4.0."
        ),
        "tempoMap": {"bpm": DEFAULT_BPM, "timeSignature": "4/4"},
        "events": [event.as_dict() for event in events],
    }
    _write_json_new(output / "reference-events.json", payload)
    write_midi(output / "reference.mid", events, tempo)
    write_musicxml(
        output / "reference.musicxml",
        events,
        tempo,
        title="Forged in Silence - Reference Drum Notation",
        artist="DrumScribe",
    )
    write_pdf(
        args.reference_pdf,
        events,
        tempo,
        title="Forged in Silence - Reference Drum Notation",
        artist="DrumScribe",
    )
    files = (
        "reference-drums.wav",
        "sealed-metal-song.wav",
        "reference-events.json",
        "reference.mid",
        "reference.musicxml",
    )
    manifest = {
        "schemaVersion": 1,
        "sealedAt": datetime.now(UTC).isoformat(),
        "seed": SEED,
        "bars": DEFAULT_BARS,
        "bpm": DEFAULT_BPM,
        "sampleRate": SAMPLE_RATE,
        "rightsCleared": True,
        "referenceOpenedByPrediction": False,
        "instrumentCounts": dict(Counter(event.instrument.value for event in events)),
        "assets": {name: _asset(output / name) for name in files},
        "referencePdf": _asset(args.reference_pdf),
        "attribution": {
            "name": "MuldjordKit FreePats",
            "license": "CC BY 4.0",
            "source": "http://freepats.zenvoid.org/Percussion/acoustic-drum-kit.html#MuldjordKit",
        },
    }
    _write_json_new(output / "sealed-manifest.json", manifest)
    print(
        json.dumps({"output": str(output), "events": len(events), "duration": duration})
    )


def predict_fixture(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    prediction = output / "prediction"
    if prediction.exists():
        raise FileExistsError(prediction)
    if args.predicted_pdf.exists():
        raise FileExistsError(args.predicted_pdf)
    full_mix = args.full_mix.resolve(strict=True)
    drum_stem = args.drum_stem.resolve(strict=True)
    prediction.mkdir()
    started = time.perf_counter()
    config = StackedEnsembleConfig.load(args.config.resolve(strict=True))
    checkpoint_paths = {
        name: (args.repository / path).resolve(strict=True)
        for name, path in CHECKPOINTS.items()
    }
    _verify_checkpoints(config, checkpoint_paths)
    feature_path = prediction / "drum-stem-features.npz"
    cache_log_mel(
        drum_stem,
        feature_path,
        PreparationConfig(seed="sealed-metal-inference", augmentation_variants=0),
    )
    arrays = np.load(feature_path)
    features = arrays["features"].astype(np.float32)
    probabilities = _stack_probabilities(
        config, checkpoint_paths, features, args.device
    )
    decoded = decode_stacked_probabilities(probabilities, config.rules)

    raw_hits: list[RawDrumHit] = []
    for class_index, instrument in enumerate(TRAINING_CLASSES):
        for frame in decoded[instrument.value]:
            confidence = float(probabilities[frame, class_index])
            raw_hits.append(
                RawDrumHit(
                    instrument,
                    onset_seconds=frame * HOP_LENGTH / 22_050,
                    velocity=max(20, min(127, round(42 + confidence * 85))),
                    confidence=confidence,
                    metadata={"provider": MODEL_VERSION, "frame": frame},
                )
            )
    raw_hits.sort(key=lambda hit: (hit.onset_seconds, str(hit.instrument_class)))
    transcription_seconds = time.perf_counter() - started

    beat_started = time.perf_counter()
    tempo = ResearchBeatThisTrackingProvider().track(full_mix)
    beat_seconds = time.perf_counter() - beat_started
    events = DefaultQuantizer().quantize(raw_hits, tempo)
    _write_json_new(
        prediction / "predicted-events.json",
        {
            "schemaVersion": 1,
            "modelVersion": config.model_version,
            "sourceAudioSha256": _sha256(full_mix),
            "drumStemSha256": _sha256(drum_stem),
            "tempoMap": _tempo_payload(tempo),
            "rawHits": [
                {
                    "instrument": str(hit.instrument_class),
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
        },
    )
    write_midi(prediction / "predicted.mid", events, tempo)
    write_musicxml(
        prediction / "predicted.musicxml",
        events,
        tempo,
        title="Forged in Silence - DrumScribe Prediction",
        artist="DrumScribe",
    )
    write_pdf(
        args.predicted_pdf,
        events,
        tempo,
        title="Forged in Silence - DrumScribe Prediction",
        artist="DrumScribe",
    )
    print(json.dumps({"prediction": str(prediction), "events": len(events)}))


def score_fixture(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    reference_payload = json.loads(
        (output / "reference-events.json").read_text(encoding="utf-8")
    )
    prediction_path = output / "prediction" / "predicted-events.json"
    prediction_payload = json.loads(prediction_path.read_text(encoding="utf-8"))
    reference = _event_rows(reference_payload["events"])
    predicted = _event_rows(prediction_payload["events"])
    reference_notation = _notation_rows(reference_payload["events"])
    predicted_notation = _notation_rows(prediction_payload["events"])

    class_50, per_class = _score_by_class(reference, predicted, 0.050)
    class_20, _ = _score_by_class(reference, predicted, 0.020)
    onset_50 = _match_times(
        [row[0] for row in reference], [row[0] for row in predicted], 0.050
    )
    notation, notation_per_class = _score_by_class(
        reference_notation, predicted_notation, 1e-6
    )
    notation_slot = _match_times(
        [row[0] for row in reference_notation],
        [row[0] for row in predicted_notation],
        1e-6,
    )
    separation = _separation_metrics(
        output / "reference-drums.wav", args.drum_stem.resolve(strict=True)
    )
    supported = [
        metric.f1
        for metric in per_class.values()
        if metric.true_positive + metric.false_negative
    ]
    result = {
        "schemaVersion": 1,
        "benchmark": "sealed-original-metal-v1",
        "track": "Forged in Silence",
        "artist": "DrumScribe",
        "modelVersion": prediction_payload["modelVersion"],
        "sealedManifestSha256": _sha256(output / "sealed-manifest.json"),
        "referenceEventsSha256": _sha256(output / "reference-events.json"),
        "predictionEventsSha256": _sha256(prediction_path),
        "referenceEvents": len(reference),
        "predictedEvents": len(predicted),
        "referenceClassCounts": dict(Counter(row[1] for row in reference)),
        "predictedClassCounts": dict(Counter(row[1] for row in predicted)),
        "classAware50ms": _metric_payload(class_50),
        "classAware20ms": _metric_payload(class_20),
        "onsetOnly50ms": _metric_payload(onset_50),
        "supportedMacroF1At50ms": statistics.fmean(supported),
        "perClass50ms": {name: _metric_payload(per_class[name]) for name in Instrument},
        "notationClassAndSlotExact": _metric_payload(notation),
        "notationSlotOnlyExact": _metric_payload(notation_slot),
        "notationPerClassExact": {
            name: _metric_payload(notation_per_class[name]) for name in Instrument
        },
        "tempo": {
            "referenceBpm": DEFAULT_BPM,
            "estimatedFirstBpm": prediction_payload["tempoMap"]["changes"][0]["bpm"],
            "estimatedMeter": prediction_payload["tempoMap"]["timeSignatures"][0],
            "estimatedOffsetSeconds": prediction_payload["tempoMap"]["offsetSeconds"],
        },
        "separation": separation,
        "timingsSeconds": prediction_payload["timingsSeconds"],
        "exactRawEventMatch": reference == predicted,
        "exactNotationMatch": reference_notation == predicted_notation,
        "testProtocol": {
            "referenceNotAvailableToPredictPhase": True,
            "predictionRunCount": 1,
            "postTestTuning": False,
            "rightsCleared": True,
        },
    }
    _write_json_new(output / "benchmark-result.json", result)
    (output / "BENCHMARK_REPORT.md").write_text(_markdown(result), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


def _render_drums(events: list[DrumEvent], kit: Path, *, duration: float) -> np.ndarray:
    result = np.zeros((math.ceil(duration * SAMPLE_RATE), 2), dtype=np.float32)
    rng = np.random.default_rng(SEED)
    catalogs = {
        instrument: sorted((kit / "samples" / folder).glob("*.flac"))
        for instrument, folder in SAMPLE_FOLDERS.items()
    }
    if any(not paths for paths in catalogs.values()):
        missing = [
            instrument.value for instrument, paths in catalogs.items() if not paths
        ]
        raise FileNotFoundError(f"MuldjordKit is missing sample folders for {missing}")
    for index, event in enumerate(events):
        if event.instrument is Instrument.TAMBOURINE:
            clip = _tambourine(rng, event.velocity)
        else:
            paths = catalogs[event.instrument]
            path = paths[(index * 17 + event.velocity) % len(paths)]
            clip, rate = sf.read(path, always_2d=True, dtype="float32")
            clip = clip.mean(axis=1)
            if rate != SAMPLE_RATE:
                length = max(1, round(len(clip) * SAMPLE_RATE / rate))
                clip = np.interp(
                    np.linspace(0, len(clip) - 1, length), np.arange(len(clip)), clip
                ).astype(np.float32)
            active = np.flatnonzero(
                np.abs(clip) > max(1e-4, float(np.max(np.abs(clip))) * 0.002)
            )
            if active.size:
                clip = clip[max(0, int(active[0]) - 8) :]
            if event.instrument is Instrument.PEDAL_HIHAT:
                clip = clip[: round(0.085 * SAMPLE_RATE)]
                clip *= np.linspace(1, 0, len(clip), dtype=np.float32)
            clip *= event.velocity / 127
        pan = PAN.get(event.instrument, 0.0)
        stereo = np.column_stack(
            (clip * math.sqrt((1 - pan) / 2), clip * math.sqrt((1 + pan) / 2))
        )
        start = round(event.onset_seconds * SAMPLE_RATE)
        end = min(len(result), start + len(stereo))
        result[start:end] += stereo[: end - start]
    return _master(result)


def _tambourine(rng: np.random.Generator, velocity: int) -> np.ndarray:
    length = round(0.22 * SAMPLE_RATE)
    noise = rng.normal(0, 1, length).astype(np.float32)
    high = np.concatenate(([noise[0]], np.diff(noise)))
    time_axis = np.arange(length) / SAMPLE_RATE
    jingles = sum(
        np.sin(2 * math.pi * frequency * time_axis)
        for frequency in (5_300, 6_750, 8_900)
    )
    envelope = np.exp(-time_axis * 17) * (
        0.55 + 0.45 * np.sin(2 * math.pi * 31 * time_axis) ** 2
    )
    return ((0.24 * high + 0.12 * jingles) * envelope * velocity / 127).astype(
        np.float32
    )


def _render_instruments(tempo: TempoMap, *, duration: float) -> np.ndarray:
    result = np.zeros((math.ceil(duration * SAMPLE_RATE), 2), dtype=np.float32)
    roots = (41.20, 43.65, 49.00, 36.71, 41.20, 55.00)
    beat_seconds = 60 / DEFAULT_BPM
    for beat in range(DEFAULT_BARS * 4):
        root = roots[(beat // 16) % len(roots)]
        start = round(tempo.beat_to_seconds(beat) * SAMPLE_RATE)
        length = round(beat_seconds * 0.92 * SAMPLE_RATE)
        time_axis = np.arange(length) / SAMPLE_RATE
        envelope = np.minimum(1, time_axis * 180) * np.exp(-time_axis * 4.8)
        bass = np.sin(2 * math.pi * root * time_axis) + 0.35 * np.sin(
            4 * math.pi * root * time_axis
        )
        bass = np.tanh(bass * 2.4) * envelope * 0.28
        end = min(len(result), start + length)
        result[start:end, 0] += bass[: end - start]
        result[start:end, 1] += bass[: end - start]
        for offset, pan in ((0.0, -0.68), (0.007, 0.68)):
            guitar_start = start + round(offset * SAMPLE_RATE)
            guitar_length = round(beat_seconds * 0.48 * SAMPLE_RATE)
            guitar_time = np.arange(guitar_length) / SAMPLE_RATE
            chord = sum(
                np.sin(2 * math.pi * root * ratio * harmonic * guitar_time) / harmonic
                for ratio in (2.0, 3.0)
                for harmonic in (1, 3, 5, 7)
            )
            guitar_envelope = np.minimum(1, guitar_time * 260) * np.exp(
                -guitar_time * 8.5
            )
            guitar = np.tanh(chord * 1.9) * guitar_envelope * 0.13
            left = guitar * math.sqrt((1 - pan) / 2)
            right = guitar * math.sqrt((1 + pan) / 2)
            guitar_end = min(len(result), guitar_start + guitar_length)
            result[guitar_start:guitar_end, 0] += left[: guitar_end - guitar_start]
            result[guitar_start:guitar_end, 1] += right[: guitar_end - guitar_start]
    return _master(result)


def _master(samples: np.ndarray) -> np.ndarray:
    shaped = np.tanh(samples * 1.15)
    peak = float(np.max(np.abs(shaped)))
    return (shaped * (0.96 / max(0.96, peak))).astype(np.float32)


def _stack_probabilities(
    config: StackedEnsembleConfig,
    checkpoint_paths: dict[str, Path],
    features: np.ndarray,
    requested_device: str,
) -> np.ndarray:
    import torch

    if requested_device == "auto":
        device = (
            "cuda"
            if torch.cuda.is_available()
            else "mps"
            if torch.backends.mps.is_available()
            else "cpu"
        )
    else:
        device = requested_device
    feature_tensor = torch.from_numpy(features)[None].to(device)
    by_model: dict[str, np.ndarray] = {}
    with torch.no_grad():
        for name, path in checkpoint_paths.items():
            state = torch.load(path, map_location="cpu", weights_only=True)
            model_config = TrainingConfig(**state["configuration"])
            model = build_model(
                model_config,
                mel_bands=features.shape[1],
                class_count=len(TRAINING_CLASSES),
            ).to(device)
            model.load_state_dict(state["model"])
            model.eval()
            by_model[name] = torch.sigmoid(model(feature_tensor)[0])[0].cpu().numpy()
    return blend_stacked_probabilities(by_model, config.rules)


def _verify_checkpoints(config: StackedEnsembleConfig, paths: dict[str, Path]) -> None:
    if set(paths) != set(config.models):
        raise ValueError("checkpoint names do not match frozen config")
    for name, path in paths.items():
        actual = _sha256(path)
        expected = config.models[name].sha256
        if actual != expected:
            raise ValueError(
                f"checkpoint hash mismatch for {name}: {actual} != {expected}"
            )


def _tempo_payload(tempo: TempoMap) -> dict[str, Any]:
    return {
        "offsetSeconds": tempo.offset_seconds,
        "changes": [
            {
                "startBeat": str(change.start_beat),
                "bpm": change.bpm,
                "confidence": change.confidence,
            }
            for change in tempo.changes
        ],
        "timeSignatures": [
            {
                "startBeat": str(signature.start_beat),
                "numerator": signature.numerator,
                "denominator": signature.denominator,
                "confidence": signature.confidence,
            }
            for signature in tempo.time_signatures
        ],
    }


def _event_rows(rows: list[dict[str, Any]]) -> list[tuple[float, Instrument]]:
    return sorted(
        ((float(row["onsetSeconds"]), Instrument(row["instrument"])) for row in rows),
        key=lambda item: (item[0], item[1]),
    )


def _fraction(value: Any) -> Fraction:
    if isinstance(value, dict):
        return Fraction(int(value["numerator"]), int(value["denominator"]))
    if isinstance(value, str):
        return Fraction(value)
    return Fraction(value)


def _notation_rows(rows: list[dict[str, Any]]) -> list[tuple[float, Instrument]]:
    return sorted(
        (
            (
                float(_fraction(row["beatPosition"])),
                Instrument(row["instrument"]),
            )
            for row in rows
            if row.get("beatPosition") is not None
        ),
        key=lambda item: (item[0], item[1]),
    )


def _match_times(
    reference: list[float], prediction: list[float], tolerance: float
) -> MatchResult:
    reference = sorted(reference)
    prediction = sorted(prediction)
    ref_index = pred_index = false_positive = false_negative = 0
    errors: list[float] = []
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


def _score_by_class(
    reference: list[tuple[float, Instrument]],
    prediction: list[tuple[float, Instrument]],
    tolerance: float,
) -> tuple[MatchResult, dict[Instrument, MatchResult]]:
    results = {
        instrument: _match_times(
            [time_value for time_value, name in reference if name is instrument],
            [time_value for time_value, name in prediction if name is instrument],
            tolerance,
        )
        for instrument in Instrument
    }
    return _combine(results.values()), results


def _combine(results: Any) -> MatchResult:
    values = tuple(results)
    return MatchResult(
        sum(item.true_positive for item in values),
        sum(item.false_positive for item in values),
        sum(item.false_negative for item in values),
        tuple(error for item in values for error in item.errors),
    )


def _metric_payload(result: MatchResult) -> dict[str, Any]:
    return {
        "truePositive": result.true_positive,
        "falsePositive": result.false_positive,
        "falseNegative": result.false_negative,
        "precision": result.precision,
        "recall": result.recall,
        "f1": result.f1,
        "meanAbsoluteTimingErrorMs": (
            statistics.fmean(result.errors) * 1_000 if result.errors else None
        ),
    }


def _separation_metrics(
    reference_path: Path, prediction_path: Path
) -> dict[str, float]:
    reference, reference_rate = sf.read(reference_path, always_2d=True, dtype="float64")
    prediction, prediction_rate = sf.read(
        prediction_path, always_2d=True, dtype="float64"
    )
    if reference_rate != prediction_rate:
        raise ValueError("separation inputs must have the same sample rate")
    reference = reference.mean(axis=1)
    prediction = prediction.mean(axis=1)
    sample_count = min(len(reference), len(prediction))
    reference = reference[:sample_count] - np.mean(reference[:sample_count])
    prediction = prediction[:sample_count] - np.mean(prediction[:sample_count])
    scale = float(
        np.dot(prediction, reference) / (np.dot(reference, reference) + 1e-12)
    )
    target = scale * reference
    noise = prediction - target
    return {
        "sampleRate": reference_rate,
        "comparedSeconds": sample_count / reference_rate,
        "siSdrDb": 10
        * math.log10(
            (float(np.dot(target, target)) + 1e-12)
            / (float(np.dot(noise, noise)) + 1e-12)
        ),
        "correlation": float(np.corrcoef(reference, prediction)[0, 1]),
    }


def _markdown(result: dict[str, Any]) -> str:
    rows = []
    for instrument in Instrument:
        item = result["perClass50ms"][instrument.value]
        rows.append(
            f"| {instrument.value} | {result['referenceClassCounts'].get(instrument.value, 0)} | "
            f"{result['predictedClassCounts'].get(instrument.value, 0)} | {item['precision']:.3f} | "
            f"{item['recall']:.3f} | {item['f1']:.3f} |"
        )
    main = result["classAware50ms"]
    onset = result["onsetOnly50ms"]
    notation = result["notationClassAndSlotExact"]
    return "\n".join(
        [
            "# Sealed original metal benchmark: Forged in Silence",
            "",
            "## Executive Summary",
            "",
            (
                f"The complete full-mix pipeline achieved **{main['f1']:.1%} class-aware F1 at "
                f"50 ms**, **{onset['f1']:.1%} onset-only F1**, and **{notation['f1']:.1%} "
                "exact notation class-and-slot F1** on its first sealed run."
            ),
            "",
            "## Per-class evidence",
            "",
            "| Class | Reference | Predicted | Precision | Recall | F1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            *rows,
            "",
            "## Test protocol",
            "",
            "- Original 24-bar metal composition; no third-party song recording.",
            "- MuldjordKit drum one-shots are CC BY 4.0; guitars and bass are code-generated.",
            "- Reference labels were unavailable to prediction; prediction was run once.",
            (
                "- Demucs isolation, frozen seven-checkpoint transcription, Beat This timing, "
                "DrumScribe quantization, MIDI, MusicXML, and PDF export were exercised."
            ),
            "- No post-test tuning was performed.",
            "",
            "## Caveats and assumptions",
            "",
            (
                "This is one deterministic synthetic-but-real-sample song, not a population "
                "accuracy estimate. The model was previously selected repeatedly on Groove "
                "validation, and Demucs/Beat This remain local research dependencies pending "
                "production license review."
            ),
            "",
        ]
    )


def _asset(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    generate = subcommands.add_parser("generate")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--kit", type=Path, required=True)
    generate.add_argument("--reference-pdf", type=Path, required=True)
    predict = subcommands.add_parser("predict")
    predict.add_argument("--output", type=Path, required=True)
    predict.add_argument("--repository", type=Path, default=Path.cwd())
    predict.add_argument("--full-mix", type=Path, required=True)
    predict.add_argument("--drum-stem", type=Path, required=True)
    predict.add_argument("--predicted-pdf", type=Path, required=True)
    predict.add_argument("--config", type=Path, required=True)
    predict.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    score = subcommands.add_parser("score")
    score.add_argument("--output", type=Path, required=True)
    score.add_argument("--drum-stem", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "generate":
        generate_fixture(args)
    elif args.command == "predict":
        predict_fixture(args)
    else:
        score_fixture(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
