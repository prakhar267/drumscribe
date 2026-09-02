#!/usr/bin/env python3
"""Generate, prepare, predict, and score rights-cleared cross-genre fixtures.

Development and holdout variants use different deterministic arrangements and
random seeds.  References are written before separation or inference so the
holdout can be used as a genuine post-freeze release gate.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel
from drumscribe_music import (
    Instrument,
    RawDrumHit,
    ResearchBeatThisTrackingProvider,
    TempoMap,
    complete_rhythm,
)
from drumscribe_music.exporters import write_midi, write_musicxml, write_pdf
from model_runners.drumscribe_hybrid_runner import transcribe
from run_competitive_drum_benchmark import competitor_events, score_taxonomies
from run_hard_metal_market_benchmark import (
    KIT_PATH,
    OFFSET_SECONDS,
    SAMPLE_RATE,
    WINDOW_SECONDS,
    _aggregate_taxonomies,
    _asset,
    _event,
    _master,
    _render_drums,
    _sha256,
    _tempo_payload,
    _write_json_new,
)


@dataclass(frozen=True, slots=True)
class GenreSpec:
    slug: str
    title: str
    genre: str
    bpm: float
    seed: int
    drum_gain: float
    backing_gain: float

    @property
    def bars(self) -> int:
        return max(6, math.ceil((WINDOW_SECONDS - OFFSET_SECONDS) * self.bpm / 240))


GENRES = (
    ("soft-pop", "Soft Pop", 84.0, 0.50, 0.86),
    ("rock", "Rock", 124.0, 0.74, 0.88),
    ("hard-rock", "Hard Rock", 148.0, 0.80, 0.92),
    ("metal", "Metal", 190.0, 0.84, 0.96),
    ("punk", "Punk", 180.0, 0.78, 0.90),
    ("funk", "Funk", 108.0, 0.60, 0.88),
    ("disco", "Disco", 120.0, 0.62, 0.90),
    ("hip-hop", "Hip-Hop", 92.0, 0.56, 0.90),
    ("rnb", "R&B", 78.0, 0.48, 0.86),
    ("jazz", "Jazz", 140.0, 0.52, 0.80),
    ("country", "Country", 112.0, 0.64, 0.84),
    ("electronic", "Electronic", 128.0, 0.58, 0.94),
)


def track_specs(variant: str) -> tuple[GenreSpec, ...]:
    if variant not in {"development", "holdout", "holdout2"}:
        raise ValueError("variant must be development, holdout, or holdout2")
    base_seed = {"development": 31_000, "holdout": 79_000, "holdout2": 113_000}[variant]
    suffix = {
        "development": "Development",
        "holdout": "Holdout A",
        "holdout2": "Holdout B",
    }[variant]
    return tuple(
        GenreSpec(
            slug=f"{index:02d}-{slug}",
            title=f"{title} {suffix}",
            genre=slug,
            bpm=bpm
            + (
                0
                if variant == "development"
                else ((index if variant == "holdout" else index + 1) % 3 - 1)
                * (4 if variant == "holdout" else 3)
            ),
            seed=base_seed + index * 101,
            drum_gain=drum_gain,
            backing_gain=backing_gain,
        )
        for index, (slug, title, bpm, drum_gain, backing_gain) in enumerate(
            GENRES, start=1
        )
    )


def _events(spec: GenreSpec, variant: str) -> tuple[TempoMap, list[Any]]:
    tempo = TempoMap.constant(spec.bpm, offset_seconds=OFFSET_SECONDS)
    event_map: dict[tuple[Fraction, Instrument], Any] = {}
    rng = np.random.default_rng(spec.seed)

    def add(position: Fraction, instrument: Instrument, velocity: int) -> None:
        event_map[(position, instrument)] = _event(
            tempo, position, instrument, max(1, min(127, velocity))
        )

    def add_steps(
        measure: int,
        positions: tuple[int, ...] | range,
        instrument: Instrument,
        velocity: int,
    ) -> None:
        for position in positions:
            accent = 7 if position % 4 == 0 else 0
            add(Fraction(measure * 16 + position, 4), instrument, velocity + accent)

    for measure in range(spec.bars):
        genre = spec.genre
        start = measure * 16
        if genre == "soft-pop":
            kicks = (
                (0, 8)
                if (measure + (variant != "development")) % 2 == 0
                else (0, 6, 10)
            )
            snares, hat_positions, hat_velocity = (4, 12), range(0, 16, 2), 49
            hat = Instrument.RIDE if measure % 5 == 4 else Instrument.CLOSED_HIHAT
            velocity = 68
        elif genre == "rock":
            kicks = (0, 6, 8, 11) if measure % 2 == 0 else (0, 3, 8, 10, 14)
            snares, hat_positions, hat_velocity = (4, 12), range(0, 16, 2), 82
            hat, velocity = Instrument.CLOSED_HIHAT, 102
        elif genre == "hard-rock":
            kicks = (0, 3, 6, 8, 10, 14)
            snares, hat_positions, hat_velocity = (4, 12), range(0, 16, 2), 91
            hat, velocity = Instrument.CLOSED_HIHAT, 112
        elif genre == "metal":
            kicks = tuple(range(0, 16, 2)) if measure % 3 else tuple(range(16))
            snares, hat_positions, hat_velocity = (4, 12), range(0, 16, 2), 98
            hat, velocity = Instrument.RIDE, 116
        elif genre == "punk":
            kicks = (0, 3, 6, 8, 11, 14)
            snares, hat_positions, hat_velocity = (2, 4, 10, 12), range(16), 86
            hat, velocity = Instrument.CLOSED_HIHAT, 109
        elif genre == "funk":
            kicks = (0, 3, 7, 10, 14) if measure % 2 == 0 else (0, 6, 9, 11, 15)
            snares, hat_positions, hat_velocity = (4, 12), range(16), 67
            hat, velocity = Instrument.CLOSED_HIHAT, 90
        elif genre == "disco":
            kicks = (0, 4, 8, 12)
            snares, hat_positions, hat_velocity = (4, 12), (0, 4, 8, 12), 77
            hat, velocity = Instrument.CLOSED_HIHAT, 99
        elif genre == "hip-hop":
            kicks = (0, 7, 10) if measure % 2 == 0 else (0, 6, 11, 14)
            snares, hat_positions, hat_velocity = (4, 12), range(0, 16, 2), 64
            hat, velocity = Instrument.CLOSED_HIHAT, 86
        elif genre == "rnb":
            kicks = (0, 6, 10) if measure % 2 == 0 else (0, 7, 11)
            snares, hat_positions, hat_velocity = (), range(0, 16, 2), 45
            hat, velocity = Instrument.CLOSED_HIHAT, 66
            add_steps(measure, (4, 12), Instrument.CROSS_STICK, 58)
        elif genre == "jazz":
            kicks = (0, 8) if measure % 3 == 0 else (0,)
            snares, hat_positions, hat_velocity = (
                (4, 12),
                (0, 3, 4, 7, 8, 11, 12, 15),
                61,
            )
            hat, velocity = Instrument.RIDE, 63
            add_steps(measure, (4, 12), Instrument.PEDAL_HIHAT, 48)
        elif genre == "country":
            kicks = (0, 8)
            snares, hat_positions, hat_velocity = (4, 12), range(0, 16, 2), 72
            hat, velocity = Instrument.CLOSED_HIHAT, 91
        else:
            kicks = (0, 4, 8, 12)
            snares, hat_positions, hat_velocity = (4, 12), (2, 6, 10, 14), 72
            hat, velocity = Instrument.CLOSED_HIHAT, 104

        add_steps(measure, kicks, Instrument.KICK, velocity)
        add_steps(measure, snares, Instrument.SNARE, velocity + 2)
        add_steps(measure, tuple(hat_positions), hat, hat_velocity)
        if genre == "disco":
            add_steps(measure, (2, 6, 10, 14), Instrument.OPEN_HIHAT, 79)
        if genre == "hip-hop" and measure % 3 == 1:
            add_steps(measure, (13, 15), Instrument.CLOSED_HIHAT, 58)
        if genre == "funk" and measure % 2:
            add_steps(measure, (10,), Instrument.OPEN_HIHAT, 73)
            add_steps(measure, (15,), Instrument.SNARE, 51)
        if measure % 4 == 0:
            add(Fraction(start, 4), Instrument.CRASH, min(124, velocity + 9))
        if measure % 4 == 3:
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
                add(
                    Fraction(start + position, 4),
                    instrument,
                    velocity - 4 + position - 12,
                )
        if genre in {"country", "electronic"} and measure % 2 == 0:
            add_steps(measure, (4, 12), Instrument.TAMBOURINE, 68)
        if variant != "development" and measure % 5 == 2:
            extra = int(rng.choice((1, 5, 9, 13)))
            add(Fraction(start + extra, 4), Instrument.KICK, velocity - 9)

    return tempo, sorted(
        event_map.values(),
        key=lambda event: (event.onset_seconds, event.instrument.value),
    )


def _backing(spec: GenreSpec, tempo: TempoMap, duration: float) -> np.ndarray:
    output = np.zeros((math.ceil(duration * SAMPLE_RATE), 2), dtype=np.float32)
    roots = (65.41, 55.0, 73.42, 49.0, 61.74, 82.41)
    rng = np.random.default_rng(spec.seed + 55_555)
    beat_seconds = 60 / spec.bpm
    sustained = spec.genre in {"soft-pop", "rnb", "jazz"}
    distorted = spec.genre in {"hard-rock", "metal", "punk"}
    syncopated = spec.genre in {"funk", "hip-hop", "electronic", "disco"}
    for measure in range(spec.bars):
        root = roots[(measure + spec.seed) % len(roots)]
        measure_start = round(tempo.beat_to_seconds(measure * 4) * SAMPLE_RATE)
        chord_length = round(beat_seconds * (3.85 if sustained else 0.82) * SAMPLE_RATE)
        chord_axis = np.arange(chord_length, dtype=np.float32) / SAMPLE_RATE
        tones = sum(
            np.sin(2 * math.pi * root * ratio * chord_axis)
            for ratio in (1.0, 1.2599, 1.4983)
        )
        attack = np.minimum(1.0, chord_axis * (5 if sustained else 90))
        envelope = attack * np.exp(-chord_axis * (0.55 if sustained else 4.2))
        chord = tones * envelope * (0.060 if sustained else 0.095)
        if distorted:
            chord = np.tanh(chord * 8.5) * 0.20
        chord_end = min(len(output), measure_start + len(chord))
        if chord_end > measure_start:
            output[measure_start:chord_end, 0] += (
                chord[: chord_end - measure_start] * 0.92
            )
            output[measure_start:chord_end, 1] += (
                chord[: chord_end - measure_start] * 1.08
            )

        pulse_positions = (0, 2, 4, 6, 8, 10, 12, 14) if syncopated else (0, 4, 8, 12)
        for position in pulse_positions:
            onset = tempo.beat_to_seconds(Fraction(measure * 16 + position, 4))
            start = round(onset * SAMPLE_RATE)
            length = max(
                1, round(beat_seconds * (0.35 if syncopated else 0.75) * SAMPLE_RATE)
            )
            axis = np.arange(length, dtype=np.float32) / SAMPLE_RATE
            detune = 1 + rng.uniform(-0.002, 0.002)
            bass = np.sin(2 * math.pi * root / 2 * detune * axis) + 0.22 * np.sin(
                2 * math.pi * root * detune * axis
            )
            bass *= np.minimum(1.0, axis * 120) * np.exp(
                -axis * (5.5 if syncopated else 2.8)
            )
            bass *= 0.13
            end = min(len(output), start + length)
            if end > start:
                output[start:end] += bass[: end - start, None]
    return _master(output)


def generate(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    kit = args.kit.resolve(strict=True)
    specs = track_specs(args.variant)
    (output / "tracks").mkdir(parents=True)
    (output / "demucs-inputs").mkdir()
    manifest_tracks: list[dict[str, Any]] = []
    for spec in specs:
        track_root = output / "tracks" / spec.slug
        track_root.mkdir()
        tempo, events = _events(spec, args.variant)
        duration = min(WINDOW_SECONDS, tempo.beat_to_seconds(spec.bars * 4) + 0.5)
        clipped = [event for event in events if event.onset_seconds < duration]
        drums = _render_drums(clipped, kit, duration, spec.seed)
        backing = _backing(spec, tempo, duration)
        full_mix = _master(spec.drum_gain * drums + spec.backing_gain * backing)
        sf.write(
            track_root / "reference-drums.wav", drums, SAMPLE_RATE, subtype="PCM_24"
        )
        sf.write(track_root / "full-mix.wav", full_mix, SAMPLE_RATE, subtype="PCM_24")
        sf.write(
            output / "demucs-inputs" / f"{spec.slug}.wav",
            full_mix,
            SAMPLE_RATE,
            subtype="PCM_24",
        )
        _write_json_new(
            track_root / "reference-events.json",
            {
                "schemaVersion": 1,
                "title": spec.title,
                "style": spec.genre,
                "tempoMap": _tempo_payload(tempo),
                "events": [event.as_dict() for event in clipped],
            },
        )
        write_midi(track_root / "reference.mid", clipped, tempo)
        write_musicxml(
            track_root / "reference.musicxml",
            clipped,
            tempo,
            title=spec.title,
            artist="DrumScribe",
        )
        write_pdf(
            track_root / "reference.pdf",
            clipped,
            tempo,
            title=spec.title,
            artist="DrumScribe",
        )
        manifest_tracks.append(
            {
                **asdict(spec),
                "eventCount": len(clipped),
                "classCounts": dict(
                    Counter(event.instrument.value for event in clipped)
                ),
                "assets": {
                    name: _asset(track_root / name)
                    for name in (
                        "full-mix.wav",
                        "reference-drums.wav",
                        "reference-events.json",
                        "reference.mid",
                        "reference.musicxml",
                        "reference.pdf",
                    )
                },
            }
        )
        print(json.dumps({"generated": spec.slug, "events": len(clipped)}), flush=True)
    _write_json_new(
        output / "suite-manifest.json",
        {
            "schemaVersion": 1,
            "suite": f"cross-genre-{args.variant}-v2",
            "variant": args.variant,
            "createdAt": datetime.now(UTC).isoformat(),
            "referenceFrozenBeforePrediction": True,
            "rightsCleared": True,
            "compositionRights": "Original deterministic arrangements generated by DrumScribe project code.",
            "drumSamples": {"name": "MuldjordKit FreePats", "license": "CC BY 4.0"},
            "tracks": manifest_tracks,
        },
    )


def prepare(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    destination = output / "prepared"
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir()
    records = []
    for spec in track_specs(args.variant):
        stem = output / "demucs" / "htdemucs_ft" / spec.slug / "drums.wav"
        feature = destination / f"{spec.slug}.npz"
        cache_log_mel(
            stem.resolve(strict=True),
            feature,
            PreparationConfig(
                seed=f"cross-genre-{args.variant}", augmentation_variants=0
            ),
        )
        records.append(
            {
                "trackId": spec.slug,
                "groupId": f"cross-genre-{args.variant}-v2",
                "split": args.variant,
                "audioPath": str(stem.resolve()),
                "annotationPath": str(
                    (output / "tracks" / spec.slug / "reference-events.json").resolve()
                ),
                "featurePath": str(feature.resolve()),
            }
        )
    _write_json_new(
        destination / "prepared-dataset.json", {"schemaVersion": 1, "records": records}
    )


def _complete_payload(
    payload: dict[str, Any],
    full_mix: Path,
    beat_tracker: ResearchBeatThisTrackingProvider,
) -> dict[str, Any]:
    completion = complete_rhythm(
        (
            RawDrumHit(
                hit["instrument"],
                float(hit["onsetSeconds"]),
                int(hit["velocity"]),
                float(hit["confidence"]),
                metadata={"sourceModel": hit.get("sourceModel")},
            )
            for hit in payload["hits"]
        ),
        beat_tracker.track(full_mix),
    )
    if not completion.applied:
        return {**payload, "rhythmCompletion": dict(completion.metadata)}
    return {
        **payload,
        "modelVersion": f"{payload['modelVersion']}+rhythm-completion-v1",
        "rhythmCompletion": dict(completion.metadata),
        "hits": [
            {
                "instrument": str(hit.instrument_class),
                "onsetSeconds": round(hit.onset_seconds, 6),
                "velocity": hit.velocity,
                "confidence": round(hit.confidence, 6),
                "sourceModel": "rhythm-completion-v1",
            }
            for hit in completion.hits
        ],
    }


def predict(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    repository = args.repository.resolve(strict=True)
    destination = output / args.prediction_name
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir()
    rows = []
    beat_tracker = ResearchBeatThisTrackingProvider(
        device=None if args.device == "auto" else args.device
    )
    for spec in track_specs(args.variant):
        payload = transcribe(
            source=(
                output / "demucs" / "htdemucs_ft" / spec.slug / "drums.wav"
            ).resolve(strict=True),
            repository=repository,
            ensemble_config=(repository / args.ensemble_config).resolve(strict=True),
            oaf_checkpoint=(repository / args.oaf_checkpoint).resolve(strict=True),
            oaf_decoder=(repository / args.oaf_decoder).resolve(strict=True),
            device=args.device,
        )
        payload = _complete_payload(
            payload,
            output / "tracks" / spec.slug / "full-mix.wav",
            beat_tracker,
        )
        target = destination / f"{spec.slug}.json"
        _write_json_new(target, payload)
        rows.append(
            {
                "track": spec.slug,
                "events": len(payload["hits"]),
                "sha256": _sha256(target),
            }
        )
        print(json.dumps(rows[-1]), flush=True)
    _write_json_new(
        destination / "prediction-manifest.json",
        {
            "schemaVersion": 1,
            "createdAt": datetime.now(UTC).isoformat(),
            "referenceFilesRead": False,
            "tracks": rows,
        },
    )


def complete_predictions(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    source = output / args.input_prediction_name
    destination = output / args.prediction_name
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir()
    beat_tracker = ResearchBeatThisTrackingProvider(
        device=None if args.device == "auto" else args.device
    )
    rows = []
    for spec in track_specs(args.variant):
        payload = json.loads((source / f"{spec.slug}.json").read_text())
        payload = _complete_payload(
            payload,
            output / "tracks" / spec.slug / "full-mix.wav",
            beat_tracker,
        )
        target = destination / f"{spec.slug}.json"
        _write_json_new(target, payload)
        rows.append(
            {
                "track": spec.slug,
                "events": len(payload["hits"]),
                "sha256": _sha256(target),
            }
        )
        print(json.dumps(rows[-1]), flush=True)
    _write_json_new(
        destination / "prediction-manifest.json",
        {
            "schemaVersion": 1,
            "createdAt": datetime.now(UTC).isoformat(),
            "referenceFilesRead": False,
            "inputPredictionName": args.input_prediction_name,
            "tracks": rows,
        },
    )


def score(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    prediction_root = output / args.prediction_name
    competitor_root = args.competitor.resolve(strict=True) if args.competitor else None
    per_track = []
    for spec in track_specs(args.variant):
        reference_payload = json.loads(
            (output / "tracks" / spec.slug / "reference-events.json").read_text()
        )
        prediction_payload = json.loads(
            (prediction_root / f"{spec.slug}.json").read_text()
        )
        reference = sorted(
            (float(event["onsetSeconds"]), str(event["instrument"]))
            for event in reference_payload["events"]
            if float(event["onsetSeconds"]) < WINDOW_SECONDS
        )
        drumscribe = sorted(
            (float(hit["onsetSeconds"]), str(hit["instrument"]))
            for hit in prediction_payload["hits"]
            if float(hit["onsetSeconds"]) < WINDOW_SECONDS
        )
        systems: dict[str, list[tuple[float, str]]] = {"drumscribe": drumscribe}
        competitor_bpm = None
        if competitor_root:
            competitor, competitor_bpm = competitor_events(
                competitor_root / f"{spec.slug}.json", WINDOW_SECONDS
            )
            systems["drum2notes"] = competitor
        scores = {
            f"{milliseconds}ms": {
                name: score_taxonomies(reference, events, milliseconds / 1000)
                for name, events in systems.items()
            }
            for milliseconds in (20, 50)
        }
        per_track.append(
            {
                **asdict(spec),
                "referenceEvents": len(reference),
                "predictedEvents": {
                    name: len(events) for name, events in systems.items()
                },
                "competitorBpm": competitor_bpm,
                "scores": scores,
            }
        )
        print(json.dumps({"scored": spec.slug}), flush=True)
    system_names = list(per_track[0]["scores"]["20ms"])
    aggregate = {
        f"{milliseconds}ms": {
            system: _aggregate_taxonomies(
                [track["scores"][f"{milliseconds}ms"][system] for track in per_track]
            )
            for system in system_names
        }
        for milliseconds in (20, 50)
    }
    destination = output / args.result_name
    _write_json_new(
        destination,
        {
            "schemaVersion": 1,
            "createdAt": datetime.now(UTC).isoformat(),
            "benchmark": {
                "name": f"12-genre {args.variant} suite",
                "trackCount": len(per_track),
                "rightsCleared": True,
                "referenceFrozenBeforePrediction": True,
            },
            "aggregate": aggregate,
            "tracks": per_track,
        },
    )
    print(
        json.dumps(
            {
                "result": str(destination),
                "aggregate20ms": {
                    name: aggregate["20ms"][name]["family6"]["micro"]["f1"]
                    for name in system_names
                },
            }
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("generate", "prepare", "predict", "complete", "score"):
        command = sub.add_parser(name)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument(
            "--variant", choices=("development", "holdout", "holdout2"), required=True
        )
        if name == "generate":
            command.add_argument("--kit", type=Path, default=KIT_PATH)
        if name == "predict":
            command.add_argument("--repository", type=Path, default=Path.cwd())
            command.add_argument(
                "--ensemble-config",
                type=Path,
                default=Path("ml/configs/groove-stacked-articulation-v16.json"),
            )
            command.add_argument(
                "--oaf-checkpoint",
                type=Path,
                default=Path("ml/models/supported-kit-oaf-v24.pt"),
            )
            command.add_argument(
                "--oaf-decoder",
                type=Path,
                default=Path(
                    "ml/models/supported-kit-oaf-v24-demucs-subframe-decoder.json"
                ),
            )
            command.add_argument("--prediction-name", default="drumscribe")
            command.add_argument(
                "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
            )
        if name == "complete":
            command.add_argument(
                "--input-prediction-name", default="baseline-hybrid-v1"
            )
            command.add_argument("--prediction-name", default="drumscribe")
            command.add_argument(
                "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
            )
        if name == "score":
            command.add_argument("--prediction-name", default="drumscribe")
            command.add_argument("--competitor", type=Path)
            command.add_argument("--result-name", default="benchmark-result.json")
    args = parser.parse_args()
    {
        "generate": generate,
        "prepare": prepare,
        "predict": predict,
        "complete": complete_predictions,
        "score": score,
    }[args.command](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
