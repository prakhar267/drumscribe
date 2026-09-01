#!/usr/bin/env python3
"""Generate, predict, and score a new supported-kit metal song."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf
from drumscribe_ml.kit_adapter import KitAdapterModel, transcribe_wav
from drumscribe_music import (
    DefaultQuantizer,
    Instrument,
    RawDrumHit,
    ResearchBeatThisTrackingProvider,
    TempoMap,
)
from drumscribe_music.exporters import write_midi, write_musicxml, write_pdf
from run_sealed_metal_benchmark import (
    _asset,
    _event,
    _event_rows,
    _master,
    _match_times,
    _metric_payload,
    _notation_rows,
    _render_drums,
    _score_by_class,
    _separation_metrics,
    _sha256,
    _tempo_payload,
    _write_json_new,
)

TITLE = "Ashes of the Machine"
ARTIST = "DrumScribe"
BPM = 192.0
BARS = 28
OFFSET_SECONDS = 0.25
SAMPLE_RATE = 44_100


def new_metal_events() -> tuple[TempoMap, list]:
    """A new arrangement, distinct from every profile-calibration pattern."""

    tempo = TempoMap.constant(BPM, offset_seconds=OFFSET_SECONDS)
    event_map = {}

    def add(beat: Fraction, instrument: Instrument, velocity: int) -> None:
        event_map[(beat, instrument)] = _event(tempo, beat, instrument, velocity)

    for measure in range(BARS):
        start = Fraction(measure * 4)
        section = measure // 4
        kick_steps = {
            0: (0, 3, 6, 8, 11, 14),
            1: (0, 2, 4, 7, 8, 10, 12, 15),
            2: (0, 1, 4, 5, 8, 9, 12, 13),
            3: (0, 3, 4, 7, 8, 11, 12, 15),
            4: (0, 2, 5, 8, 10, 13),
            5: (0, 2, 4, 6, 8, 10, 12, 14),
            6: (0, 1, 2, 4, 6, 8, 9, 10, 12, 14),
        }[section]
        for step in kick_steps:
            add(
                start + Fraction(step, 4),
                Instrument.KICK,
                114 if step % 4 == 0 else 97,
            )

        if section == 0:
            for beat in (1, 3):
                add(start + beat, Instrument.CROSS_STICK, 83)
            for step in range(0, 16, 2):
                add(start + Fraction(step, 4), Instrument.CLOSED_HIHAT, 84)
        else:
            for beat in (1, 3):
                add(start + beat, Instrument.SNARE, 118)

        if section == 1:
            for step in range(0, 16, 2):
                add(start + Fraction(step, 4), Instrument.RIDE, 91)
            for beat in range(4):
                add(start + beat, Instrument.RIDE_BELL, 103)
        elif section == 2:
            for step in range(16):
                add(start + Fraction(step, 4), Instrument.CLOSED_HIHAT, 76 + step % 4)
            add(start + Fraction(15, 4), Instrument.OPEN_HIHAT, 105)
        elif section == 3:
            for step in range(0, 16, 2):
                add(start + Fraction(step, 4), Instrument.RIDE, 94)
            if measure % 2:
                add(start + Fraction(7, 2), Instrument.OPEN_HIHAT, 106)
        elif section == 4:
            for step in range(1, 16, 2):
                add(start + Fraction(step, 4), Instrument.PEDAL_HIHAT, 82)
            for beat in range(4):
                add(start + beat, Instrument.CLOSED_HIHAT, 88)
        elif section == 5:
            for step in range(0, 16, 2):
                add(start + Fraction(step, 4), Instrument.TAMBOURINE, 92)
            for beat in range(4):
                add(start + beat, Instrument.CLOSED_HIHAT, 81)
        elif section == 6:
            for step in range(0, 16, 2):
                add(start + Fraction(step, 4), Instrument.RIDE, 96)
            for beat in (0, 2):
                add(start + beat, Instrument.CRASH, 113)

        if measure % 4 == 0:
            add(start, Instrument.CRASH, 122)
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
                add(start + Fraction(step, 4), instrument, 108 + (step - 12) * 3)

    events = sorted(
        event_map.values(),
        key=lambda event: (event.onset_seconds, event.instrument.value),
    )
    return tempo, events


def _backing(
    tempo: TempoMap,
    duration: float,
    *,
    bpm: float = BPM,
    bars: int = BARS,
) -> np.ndarray:
    result = np.zeros((math.ceil(duration * SAMPLE_RATE), 2), dtype=np.float32)
    roots = (41.20, 43.65, 36.71, 49.00, 55.00, 46.25, 41.20)
    beat_seconds = 60 / bpm
    for beat in range(bars * 4):
        root = roots[(beat // 16) % len(roots)]
        start = round(tempo.beat_to_seconds(beat) * SAMPLE_RATE)
        bass_length = round(beat_seconds * 0.9 * SAMPLE_RATE)
        axis = np.arange(bass_length) / SAMPLE_RATE
        envelope = np.minimum(1, axis * 190) * np.exp(-axis * 4.9)
        bass = np.tanh(
            (
                np.sin(2 * math.pi * root * axis)
                + 0.34 * np.sin(4 * math.pi * root * axis)
            )
            * 2.4
        )
        end = min(len(result), start + bass_length)
        result[start:end] += (bass[: end - start] * envelope[: end - start] * 0.22)[
            :, None
        ]
        for offset, pan in ((0.0, -0.7), (0.0065, 0.7)):
            guitar_start = start + round(offset * SAMPLE_RATE)
            guitar_length = round(beat_seconds * 0.5 * SAMPLE_RATE)
            guitar_axis = np.arange(guitar_length) / SAMPLE_RATE
            chord = sum(
                np.sin(2 * math.pi * root * ratio * harmonic * guitar_axis) / harmonic
                for ratio in (2, 3)
                for harmonic in (1, 3, 5, 7)
            )
            guitar = (
                np.tanh(chord * 2.0)
                * np.minimum(1, guitar_axis * 280)
                * np.exp(-guitar_axis * 8.8)
                * 0.13
            )
            guitar_end = min(len(result), guitar_start + guitar_length)
            count = guitar_end - guitar_start
            result[guitar_start:guitar_end, 0] += guitar[:count] * math.sqrt(
                (1 - pan) / 2
            )
            result[guitar_start:guitar_end, 1] += guitar[:count] * math.sqrt(
                (1 + pan) / 2
            )
    return _master(result)


def generate(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    tempo, events = new_metal_events()
    duration = tempo.beat_to_seconds(BARS * 4) + 1.25
    drums = _render_drums(events, args.kit.resolve(strict=True), duration=duration)
    backing = _backing(tempo, duration)
    full_mix = _master(0.82 * drums + 0.92 * backing)
    drums_path = output / "reference-drums.wav"
    mix_path = output / "full-mix.wav"
    sf.write(drums_path, drums, SAMPLE_RATE, subtype="PCM_24")
    sf.write(mix_path, full_mix, SAMPLE_RATE, subtype="PCM_24")
    reference_path = output / "reference-events.json"
    _write_json_new(
        reference_path,
        {
            "schemaVersion": 1,
            "title": TITLE,
            "tempoMap": _tempo_payload(tempo),
            "events": [event.as_dict() for event in events],
        },
    )
    write_midi(output / "reference.mid", events, tempo)
    write_musicxml(
        output / "reference.musicxml", events, tempo, title=TITLE, artist=ARTIST
    )
    write_pdf(output / "reference.pdf", events, tempo, title=TITLE, artist=ARTIST)
    _write_json_new(
        output / "sealed-manifest.json",
        {
            "schemaVersion": 1,
            "benchmark": "supported-kit-new-metal-v1",
            "title": TITLE,
            "compositionPreviouslyUsedForTraining": False,
            "kitProfile": "MuldjordKit/FreePats",
            "assistedBpm": BPM,
            "assistedOffsetSeconds": OFFSET_SECONDS,
            "instrumentCounts": dict(
                Counter(event.instrument.value for event in events)
            ),
            "rightsCleared": True,
            "assets": {
                name: _asset(output / name)
                for name in (
                    "full-mix.wav",
                    "reference-drums.wav",
                    "reference-events.json",
                )
            },
        },
    )
    print(
        json.dumps({"output": str(output), "events": len(events), "duration": duration})
    )


def predict(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    prediction = output / "prediction"
    if prediction.exists():
        raise FileExistsError(prediction)
    prediction.mkdir()
    model_path = args.model.resolve(strict=True)
    full_mix = args.full_mix.resolve(strict=True)
    drum_stem = args.drum_stem.resolve(strict=True)
    started = time.perf_counter()
    model = KitAdapterModel.load(model_path)
    detected = transcribe_wav(drum_stem, model)
    transcription_seconds = time.perf_counter() - started
    raw_hits = [
        RawDrumHit(
            instrument_class=item.instrument,
            onset_seconds=item.onset_seconds,
            velocity=item.velocity,
            confidence=item.confidence,
            metadata={"provider": model.model_version},
        )
        for item in detected
    ]
    beat_started = time.perf_counter()
    estimated_tempo = ResearchBeatThisTrackingProvider().track(full_mix)
    beat_seconds = time.perf_counter() - beat_started
    assisted_tempo = TempoMap.constant(
        args.bpm_hint,
        offset_seconds=args.offset_hint,
    )
    events = DefaultQuantizer().quantize(raw_hits, assisted_tempo)
    payload = {
        "schemaVersion": 1,
        "modelVersion": model.model_version,
        "modelSha256": _sha256(model_path),
        "sourceAudioSha256": _sha256(full_mix),
        "drumStemSha256": _sha256(drum_stem),
        "estimatedTempoMap": _tempo_payload(estimated_tempo),
        "assistedTempoMap": _tempo_payload(assisted_tempo),
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
            "beatTrackingDiagnostic": beat_seconds,
            "total": time.perf_counter() - started,
        },
    }
    prediction_path = prediction / "predicted-events.json"
    _write_json_new(prediction_path, payload)
    write_midi(prediction / "predicted.mid", events, assisted_tempo)
    write_musicxml(
        prediction / "predicted.musicxml",
        events,
        assisted_tempo,
        title=f"{TITLE} - Prediction",
        artist=ARTIST,
    )
    write_pdf(
        prediction / "predicted.pdf",
        events,
        assisted_tempo,
        title=f"{TITLE} - Prediction",
        artist=ARTIST,
    )
    print(json.dumps({"prediction": str(prediction), "events": len(events)}))


def score(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    reference_path = output / "reference-events.json"
    prediction_path = output / "prediction" / "predicted-events.json"
    reference = json.loads(reference_path.read_text())
    prediction = json.loads(prediction_path.read_text())
    reference_rows = _event_rows(reference["events"])
    predicted_rows = sorted(
        (
            (float(row["onsetSeconds"]), Instrument(row["instrument"]))
            for row in prediction["rawHits"]
        ),
        key=lambda item: (item[0], item[1].value),
    )
    class_metric, per_class = _score_by_class(reference_rows, predicted_rows, 0.050)
    onset_metric = _match_times(
        [item[0] for item in reference_rows],
        [item[0] for item in predicted_rows],
        0.050,
    )
    reference_notation = _notation_rows(reference["events"])
    predicted_notation = _notation_rows(prediction["events"])
    notation_metric, notation_per_class = _score_by_class(
        reference_notation, predicted_notation, 1e-6
    )
    supported = [
        value.f1
        for value in per_class.values()
        if value.true_positive + value.false_negative
    ]
    result = {
        "schemaVersion": 1,
        "benchmark": "supported-kit-new-metal-v1",
        "track": TITLE,
        "modelVersion": prediction["modelVersion"],
        "referenceEvents": len(reference_rows),
        "predictedEvents": len(predicted_rows),
        "referenceClassCounts": dict(Counter(item[1].value for item in reference_rows)),
        "predictedClassCounts": dict(Counter(item[1].value for item in predicted_rows)),
        "classAware50ms": _metric_payload(class_metric),
        "onsetOnly50ms": _metric_payload(onset_metric),
        "supportedMacroF1At50ms": statistics.fmean(supported),
        "perClass50ms": {
            instrument.value: _metric_payload(per_class[instrument])
            for instrument in Instrument
        },
        "notationClassAndSlotExact": _metric_payload(notation_metric),
        "notationPerClassExact": {
            instrument.value: _metric_payload(notation_per_class[instrument])
            for instrument in Instrument
        },
        "separation": _separation_metrics(
            output / "reference-drums.wav", args.drum_stem.resolve(strict=True)
        ),
        "tempo": {
            "assistedBpm": BPM,
            "estimatedFirstBpm": prediction["estimatedTempoMap"]["changes"][0]["bpm"],
        },
        "testProtocol": {
            "newComposition": True,
            "knownSupportedKitProfile": True,
            "bpmAndOffsetHintsProvided": True,
            "successfulPredictionRunCount": 1,
            "failedPreSerializationInvocations": 1,
            "failedInvocationUsedReference": False,
            "postTestTuning": False,
            "rightsCleared": True,
        },
    }
    _write_json_new(output / "benchmark-result.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate_parser = commands.add_parser("generate")
    generate_parser.add_argument("--output", type=Path, required=True)
    generate_parser.add_argument("--kit", type=Path, required=True)
    predict_parser = commands.add_parser("predict")
    predict_parser.add_argument("--output", type=Path, required=True)
    predict_parser.add_argument("--full-mix", type=Path, required=True)
    predict_parser.add_argument("--drum-stem", type=Path, required=True)
    predict_parser.add_argument("--model", type=Path, required=True)
    predict_parser.add_argument("--bpm-hint", type=float, required=True)
    predict_parser.add_argument("--offset-hint", type=float, required=True)
    score_parser = commands.add_parser("score")
    score_parser.add_argument("--output", type=Path, required=True)
    score_parser.add_argument("--drum-stem", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        generate(args)
    elif args.command == "predict":
        predict(args)
    else:
        score(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
