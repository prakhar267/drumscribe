#!/usr/bin/env python3
"""Generate and score ten new rights-cleared hard-metal full-mix fixtures.

The suite uses original programmed drum parts rendered with the CC BY 4.0
MuldjordKit and code-generated distorted guitar/bass backing.  References are
frozen before separation or prediction.  ``predict`` never reads the reference
event files; ``score`` opens them only after both products have produced output.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from drumscribe_ml.ensemble import StackedEnsembleConfig
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel
from drumscribe_music import DefaultQuantizer, Instrument, RawDrumHit, TempoMap
from drumscribe_music.exporters import write_midi, write_musicxml, write_pdf
from drumscribe_music.providers.research import ResearchBeatThisTrackingProvider
from run_competitive_drum_benchmark import (
    CHECKPOINTS,
    competitor_events,
    load_models,
    metrics_from_counts,
    predict_drumscribe,
    score_taxonomies,
)
from run_sealed_metal_benchmark import (
    _asset,
    _event,
    _master,
    _separation_metrics,
    _sha256,
    _tempo_payload,
    _write_json_new,
)

SAMPLE_RATE = 44_100
OFFSET_SECONDS = 0.25
WINDOW_SECONDS = 20.0
MODEL_CONFIG = Path("ml/configs/groove-stacked-articulation-v16.json")
KIT_PATH = Path("data/licensed-corpus/freepats-muldjordkit")


@dataclass(frozen=True, slots=True)
class TrackSpec:
    slug: str
    title: str
    style: str
    bpm: float
    seed: int

    @property
    def bars(self) -> int:
        return max(6, round(self.bpm * 18.0 / 240.0))


TRACKS = (
    TrackSpec("01-thrash-assault", "Chromium Assault", "thrash", 198.0, 101),
    TrackSpec("02-nu-metal-breakdown", "Concrete Pulse", "nu-metal", 104.0, 202),
    TrackSpec("03-metalcore-drive", "Fractured Signal", "metalcore", 156.0, 303),
    TrackSpec("04-death-metal-blast", "Terminal Velocity", "death-metal", 220.0, 404),
    TrackSpec("05-doom-weight", "Gravity Well", "doom-metal", 72.0, 505),
    TrackSpec("06-groove-metal", "Iron Circuit", "groove-metal", 122.0, 606),
    TrackSpec("07-industrial-metal", "Machine Ritual", "industrial-metal", 128.0, 707),
    TrackSpec("08-progressive-metal", "Odd Horizon", "progressive-metal", 138.0, 808),
    TrackSpec("09-power-metal-gallop", "Solar Vanguard", "power-metal", 184.0, 909),
    TrackSpec("10-hardcore-dbeat", "Rusted Crown", "hardcore", 192.0, 1010),
)


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


def _events(spec: TrackSpec) -> tuple[TempoMap, list[Any]]:
    tempo = TempoMap.constant(spec.bpm, offset_seconds=OFFSET_SECONDS)
    rng = np.random.default_rng(spec.seed)
    event_map: dict[tuple[Fraction, Instrument], Any] = {}

    def add(step: int, instrument: Instrument, velocity: int) -> None:
        beat = Fraction(step, 4)
        event_map[(beat, instrument)] = _event(tempo, beat, instrument, velocity)

    def hats(measure_start: int, pattern: str) -> None:
        if pattern == "sixteenth":
            positions = range(16)
        elif pattern == "eighth":
            positions = range(0, 16, 2)
        else:
            positions = range(0, 16, 4)
        for position in positions:
            instrument = Instrument.CLOSED_HIHAT
            if position == 15 or (
                pattern != "quarter" and position == 14 and rng.random() < 0.35
            ):
                instrument = Instrument.OPEN_HIHAT
            elif position in {5, 13} and spec.style in {"nu-metal", "groove-metal"}:
                instrument = Instrument.PEDAL_HIHAT
            add(measure_start + position, instrument, 78 + 13 * (position % 4 == 0))

    for measure in range(spec.bars):
        start = measure * 16
        style = spec.style
        if style == "thrash":
            kicks = (0, 2, 4, 6, 8, 10, 12, 14) if measure % 4 else tuple(range(16))
            snares = (4, 12)
            hats(start, "eighth")
        elif style == "nu-metal":
            kicks = (0, 3, 6, 10, 11, 15) if measure % 2 else (0, 2, 7, 8, 11, 14)
            snares = (8,)
            hats(start, "eighth")
        elif style == "metalcore":
            kicks = (0, 1, 4, 6, 8, 9, 12, 14)
            snares = (4, 12)
            hats(start, "sixteenth" if measure % 3 == 1 else "eighth")
        elif style == "death-metal":
            kicks = tuple(range(16)) if measure % 2 == 0 else tuple(range(0, 16, 2))
            snares = tuple(range(1, 16, 2)) if measure % 4 == 2 else (4, 12)
            for position in range(0, 16, 2):
                add(start + position, Instrument.RIDE, 91 + 7 * (position % 4 == 0))
        elif style == "doom-metal":
            kicks = (0, 7, 10)
            snares = (8,)
            hats(start, "quarter")
        elif style == "groove-metal":
            kicks = (0, 3, 4, 7, 10, 11, 14)
            snares = (4, 12)
            hats(start, "eighth")
        elif style == "industrial-metal":
            kicks = (0, 2, 6, 8, 10, 14)
            snares = (4, 12)
            hats(start, "sixteenth")
            for position in range(0, 16, 4):
                add(start + position, Instrument.TAMBOURINE, 72)
        elif style == "progressive-metal":
            patterns = (
                (0, 3, 5, 8, 11, 13),
                (0, 2, 6, 7, 10, 14),
                (0, 1, 4, 9, 12, 15),
            )
            kicks = patterns[measure % len(patterns)]
            snares = (4, 11) if measure % 2 else (5, 12)
            hats(start, "eighth")
        elif style == "power-metal":
            kicks = (0, 1, 3, 4, 5, 7, 8, 9, 11, 12, 13, 15)
            snares = (4, 12)
            for position in range(0, 16, 2):
                add(start + position, Instrument.RIDE, 92)
        else:  # hardcore d-beat
            kicks = (0, 3, 6, 8, 11, 14)
            snares = (2, 4, 10, 12)
            hats(start, "eighth")

        for position in kicks:
            add(start + position, Instrument.KICK, 113 if position % 4 == 0 else 98)
        for position in snares:
            add(start + position, Instrument.SNARE, 116 if position % 4 == 0 else 104)

        if measure % 4 == 0:
            add(start, Instrument.CRASH, 122)
        if measure % 6 == 3:
            add(start, Instrument.RIDE_BELL, 106)
        if style == "nu-metal" and measure == 0:
            add(start + 8, Instrument.CROSS_STICK, 94)
        if measure % 4 == 3:
            fill = (
                Instrument.HIGH_TOM,
                Instrument.MID_TOM,
                Instrument.LOW_TOM,
                Instrument.FLOOR_TOM,
            )
            for position, instrument in zip((12, 13, 14, 15), fill, strict=True):
                add(start + position, instrument, 105 + (position - 12) * 3)

    events = sorted(
        event_map.values(),
        key=lambda event: (event.onset_seconds, event.instrument.value),
    )
    return tempo, events


def _render_drums(
    events: list[Any], kit: Path, duration: float, seed: int
) -> np.ndarray:
    output = np.zeros((math.ceil(duration * SAMPLE_RATE), 2), dtype=np.float32)
    rng = np.random.default_rng(seed)
    catalogs = {
        instrument: sorted((kit / "samples" / folder).glob("*.flac"))
        for instrument, folder in SAMPLE_FOLDERS.items()
    }
    if any(not paths for paths in catalogs.values()):
        raise FileNotFoundError("MuldjordKit sample catalog is incomplete")
    for index, event in enumerate(events):
        if event.instrument is Instrument.TAMBOURINE:
            clip = _tambourine(rng, event.velocity)
        else:
            paths = catalogs[event.instrument]
            path = paths[(index * 17 + event.velocity + seed) % len(paths)]
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
        end = min(len(output), start + len(stereo))
        output[start:end] += stereo[: end - start]
    return _master(output)


def _tambourine(rng: np.random.Generator, velocity: int) -> np.ndarray:
    length = round(0.22 * SAMPLE_RATE)
    noise = rng.normal(0, 1, length).astype(np.float32)
    high = np.concatenate(([noise[0]], np.diff(noise)))
    axis = np.arange(length) / SAMPLE_RATE
    jingles = sum(
        np.sin(2 * math.pi * frequency * axis) for frequency in (5_300, 6_750, 8_900)
    )
    envelope = np.exp(-axis * 17) * (0.55 + 0.45 * np.sin(2 * math.pi * 31 * axis) ** 2)
    return ((0.24 * high + 0.12 * jingles) * envelope * velocity / 127).astype(
        np.float32
    )


def _chug_positions(style: str, measure: int) -> tuple[int, ...]:
    return {
        "thrash": tuple(range(0, 16, 2)),
        "nu-metal": (0, 3, 6, 10, 11, 15),
        "metalcore": (0, 1, 4, 6, 8, 9, 12, 14),
        "death-metal": tuple(range(16)),
        "doom-metal": (0, 8),
        "groove-metal": (0, 3, 4, 7, 10, 11, 14),
        "industrial-metal": (0, 2, 6, 8, 10, 14),
        "progressive-metal": ((0, 3, 5, 8, 11, 13), (0, 2, 6, 7, 10, 14))[measure % 2],
        "power-metal": (0, 3, 4, 7, 8, 11, 12, 15),
        "hardcore": (0, 3, 6, 8, 11, 14),
    }[style]


def _render_backing(spec: TrackSpec, tempo: TempoMap, duration: float) -> np.ndarray:
    output = np.zeros((math.ceil(duration * SAMPLE_RATE), 2), dtype=np.float32)
    roots = (41.20, 43.65, 36.71, 49.00, 55.00, 46.25)
    step_seconds = 60.0 / spec.bpm / 4.0
    rng = np.random.default_rng(spec.seed + 9000)
    for measure in range(spec.bars):
        root = roots[(measure + spec.seed) % len(roots)]
        for position in _chug_positions(spec.style, measure):
            onset = tempo.beat_to_seconds(Fraction(measure * 4) + Fraction(position, 4))
            start = round(onset * SAMPLE_RATE)
            length = round(
                step_seconds
                * (1.7 if spec.style == "doom-metal" else 0.88)
                * SAMPLE_RATE
            )
            axis = np.arange(length) / SAMPLE_RATE
            detune = 1 + rng.uniform(-0.0025, 0.0025)
            harmonics = sum(
                np.sin(2 * math.pi * root * detune * ratio * harmonic * axis) / harmonic
                for ratio in (2.0, 3.0)
                for harmonic in (1, 3, 5, 7)
            )
            envelope = np.minimum(1, axis * 300) * np.exp(
                -axis * (7.2 if spec.style == "doom-metal" else 15.0)
            )
            guitar = np.tanh(harmonics * 2.2) * envelope * 0.16
            for delay, pan in ((0.0, -0.72), (0.0065, 0.72)):
                guitar_start = start + round(delay * SAMPLE_RATE)
                end = min(len(output), guitar_start + len(guitar))
                count = max(0, end - guitar_start)
                if count:
                    output[guitar_start:end, 0] += guitar[:count] * math.sqrt(
                        (1 - pan) / 2
                    )
                    output[guitar_start:end, 1] += guitar[:count] * math.sqrt(
                        (1 + pan) / 2
                    )

        for beat in range(4):
            onset = tempo.beat_to_seconds(measure * 4 + beat)
            start = round(onset * SAMPLE_RATE)
            length = round(60.0 / spec.bpm * 0.92 * SAMPLE_RATE)
            axis = np.arange(length) / SAMPLE_RATE
            bass = np.tanh(
                (
                    np.sin(2 * math.pi * root * axis)
                    + 0.38 * np.sin(4 * math.pi * root * axis)
                )
                * 2.7
            )
            bass *= np.minimum(1, axis * 180) * np.exp(-axis * 4.5) * 0.24
            end = min(len(output), start + len(bass))
            output[start:end] += bass[: end - start, None]
    return _master(output)


def generate_suite(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    kit = args.kit.resolve(strict=True)
    output.mkdir(parents=True)
    manifest_tracks = []
    for spec in TRACKS:
        track_root = output / "tracks" / spec.slug
        track_root.mkdir(parents=True)
        tempo, events = _events(spec)
        duration = min(20.0, tempo.beat_to_seconds(spec.bars * 4) + 1.0)
        drums = _render_drums(events, kit, duration, spec.seed)
        backing = _render_backing(spec, tempo, duration)
        full_mix = _master(0.76 * drums + 0.96 * backing)
        drums_path = track_root / "reference-drums.wav"
        mix_path = track_root / "full-mix.wav"
        reference_path = track_root / "reference-events.json"
        sf.write(drums_path, drums, SAMPLE_RATE, subtype="PCM_24")
        sf.write(mix_path, full_mix, SAMPLE_RATE, subtype="PCM_24")
        _write_json_new(
            reference_path,
            {
                "schemaVersion": 1,
                "title": spec.title,
                "style": spec.style,
                "tempoMap": _tempo_payload(tempo),
                "events": [
                    event.as_dict()
                    for event in events
                    if event.onset_seconds < duration
                ],
            },
        )
        clipped_events = [event for event in events if event.onset_seconds < duration]
        write_midi(track_root / "reference.mid", clipped_events, tempo)
        write_musicxml(
            track_root / "reference.musicxml",
            clipped_events,
            tempo,
            title=f"{spec.title} - Reference",
            artist="DrumScribe",
        )
        write_pdf(
            track_root / "reference.pdf",
            clipped_events,
            tempo,
            title=f"{spec.title} - Reference",
            artist="DrumScribe",
        )
        manifest_tracks.append(
            {
                **asdict(spec),
                "bars": spec.bars,
                "durationSeconds": duration,
                "eventCount": len(clipped_events),
                "classCounts": dict(
                    Counter(event.instrument.value for event in clipped_events)
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
        print(
            json.dumps(
                {
                    "generated": spec.slug,
                    "duration": duration,
                    "events": len(clipped_events),
                }
            ),
            flush=True,
        )
    _write_json_new(
        output / "suite-manifest.json",
        {
            "schemaVersion": 1,
            "suite": getattr(args, "suite_name", "hard-metal-originals-v1"),
            "sealedAt": datetime.now(UTC).isoformat(),
            "referenceFrozenBeforePrediction": True,
            "rightsCleared": True,
            "compositionRights": "Original deterministic arrangements generated by DrumScribe project code.",
            "drumSamples": {
                "name": "MuldjordKit FreePats",
                "license": "CC BY 4.0",
                "source": "https://freepats.zenvoid.org/Percussion/acoustic-drum-kits.html",
            },
            "backing": "Code-generated distorted guitar and bass synthesis; no third-party recording.",
            "tracks": manifest_tracks,
        },
    )


def _resolve(repository: Path, path: Path) -> Path:
    return (
        (repository / path).resolve(strict=True)
        if not path.is_absolute()
        else path.resolve(strict=True)
    )


def predict_suite(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    repository = args.repository.resolve(strict=True)
    destination = output / "drumscribe"
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir()
    config_path = _resolve(repository, args.config)
    config = StackedEnsembleConfig.load(config_path)
    checkpoint_paths = {
        name: _resolve(repository, CHECKPOINTS[name]) for name in config.models
    }
    first_stem = (
        args.demucs_root.resolve(strict=True)
        / "htdemucs_ft"
        / TRACKS[0].slug
        / "drums.wav"
    )
    first_feature = destination / "first-features.npz"
    cache_log_mel(
        first_stem,
        first_feature,
        PreparationConfig(seed="hard-metal-suite-first", augmentation_variants=0),
    )
    mel_bands = int(np.load(first_feature)["features"].shape[1])

    import torch

    device = args.device
    if device == "auto":
        device = (
            "cuda"
            if torch.cuda.is_available()
            else "mps"
            if torch.backends.mps.is_available()
            else "cpu"
        )
    models = load_models(config, checkpoint_paths, mel_bands, device)
    beat_tracker = ResearchBeatThisTrackingProvider(device=device)
    summary = []
    for spec in TRACKS:
        started = time.perf_counter()
        track_root = output / "tracks" / spec.slug
        mix_path = track_root / "full-mix.wav"
        stem_path = (
            args.demucs_root.resolve(strict=True)
            / "htdemucs_ft"
            / spec.slug
            / "drums.wav"
        )
        prediction_root = destination / spec.slug
        prediction_root.mkdir()
        feature_path = prediction_root / "features.npz"
        cache_log_mel(
            stem_path,
            feature_path,
            PreparationConfig(seed=f"hard-metal-{spec.slug}", augmentation_variants=0),
        )
        predicted_rows = predict_drumscribe(
            feature_path, models, config, device, WINDOW_SECONDS
        )
        raw_hits = [
            RawDrumHit(
                Instrument(instrument),
                onset_seconds=onset,
                velocity=100,
                confidence=1.0,
                metadata={"provider": config.model_version},
            )
            for onset, instrument in predicted_rows
        ]
        tempo_started = time.perf_counter()
        tempo = beat_tracker.track(mix_path)
        tempo_seconds = time.perf_counter() - tempo_started
        notation_events = DefaultQuantizer().quantize(raw_hits, tempo)
        payload = {
            "schemaVersion": 1,
            "modelVersion": config.model_version,
            "sourceAudioSha256": _sha256(mix_path),
            "drumStemSha256": _sha256(stem_path),
            "tempoMap": _tempo_payload(tempo),
            "rawHits": [
                {"onsetSeconds": onset, "instrument": instrument}
                for onset, instrument in predicted_rows
            ],
            "events": [event.as_dict() for event in notation_events],
            "timingsSeconds": {
                "tempo": tempo_seconds,
                "total": time.perf_counter() - started,
            },
        }
        _write_json_new(prediction_root / "predicted-events.json", payload)
        write_midi(prediction_root / "predicted.mid", notation_events, tempo)
        write_musicxml(
            prediction_root / "predicted.musicxml",
            notation_events,
            tempo,
            title=f"{spec.title} - DrumScribe",
            artist="DrumScribe",
        )
        summary.append(
            {
                "track": spec.slug,
                "events": len(predicted_rows),
                "seconds": payload["timingsSeconds"]["total"],
            }
        )
        print(json.dumps(summary[-1]), flush=True)
    first_feature.unlink(missing_ok=True)
    _write_json_new(
        destination / "prediction-manifest.json",
        {
            "schemaVersion": 1,
            "modelVersion": config.model_version,
            "configSha256": _sha256(config_path),
            "checkpointSha256": {
                name: _sha256(path) for name, path in sorted(checkpoint_paths.items())
            },
            "referenceFilesRead": False,
            "device": device,
            "tracks": summary,
        },
    )


def _fraction(value: Any) -> Fraction:
    if isinstance(value, dict):
        return Fraction(int(value["numerator"]), int(value["denominator"]))
    return Fraction(str(value))


def _notation_rows(events: list[dict[str, Any]]) -> list[tuple[float, str]]:
    return sorted(
        (float(_fraction(event["beatPosition"])), str(event["instrument"]))
        for event in events
        if event.get("beatPosition") is not None
    )


def _competitor_notation(path: Path, limit: float) -> list[tuple[float, str]]:
    from drumscribe_music.mapping import GM_TO_INSTRUMENT

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for part in payload.get("Parts", []):
        for measure_index, measure in enumerate(part.get("Measures", [])):
            timestamp = float(measure.get("TimeStamp", 0.0))
            if timestamp >= limit:
                continue
            for voice in measure.get("Voices", []):
                cursor = 0.0
                for note in voice.get("Notes", []):
                    instruments = {
                        GM_TO_INSTRUMENT[midi].value
                        for midi in note.get("Midi", [])
                        if isinstance(midi, int) and midi in GM_TO_INSTRUMENT
                    }
                    rows.extend(
                        (measure_index * 4 + cursor * 4, instrument)
                        for instrument in instruments
                    )
                    cursor += float(note.get("Duration", 0.0))
    return sorted(rows)


def _aggregate_scores(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate already-scored tracks without perturbing onset timestamps.

    Re-scoring concatenated tracks after adding a large floating-point offset can
    flip events that land exactly on a tolerance boundary.  Summing the per-track
    confusion counts is mathematically equivalent and numerically stable.
    """

    per_class: dict[str, dict[str, Any]] = {}
    classes = sorted(
        {instrument for block in blocks for instrument in block["perClass"]}
    )
    for instrument in classes:
        class_blocks = [
            block["perClass"].get(
                instrument,
                {"tp": 0, "fp": 0, "fn": 0, "support": 0},
            )
            for block in blocks
        ]
        tp = sum(int(item["tp"]) for item in class_blocks)
        fp = sum(int(item["fp"]) for item in class_blocks)
        fn = sum(int(item["fn"]) for item in class_blocks)
        metrics = metrics_from_counts(tp, fp, fn)
        metrics["support"] = sum(int(item["support"]) for item in class_blocks)
        timing_weight = sum(
            int(item["tp"])
            for item in class_blocks
            if "meanAbsoluteTimingErrorMs" in item
        )
        if timing_weight:
            metrics["meanAbsoluteTimingErrorMs"] = (
                sum(
                    float(item.get("meanAbsoluteTimingErrorMs", 0.0)) * int(item["tp"])
                    for item in class_blocks
                )
                / timing_weight
            )
        per_class[instrument] = metrics

    micro_counts = {
        key: sum(int(block["micro"][key]) for block in blocks)
        for key in ("tp", "fp", "fn")
    }
    onset_counts = {
        key: sum(int(block["classAgnostic"][key]) for block in blocks)
        for key in ("tp", "fp", "fn")
    }
    result: dict[str, Any] = {
        "micro": metrics_from_counts(**micro_counts),
        "supportedMacroF1": statistics.mean(
            float(metrics["f1"])
            for metrics in per_class.values()
            if int(metrics["support"]) > 0
        ),
        "supportedClassCount": sum(
            int(metrics["support"]) > 0 for metrics in per_class.values()
        ),
        "classAgnostic": metrics_from_counts(**onset_counts),
        "referenceEvents": sum(int(block["referenceEvents"]) for block in blocks),
        "predictedEvents": sum(int(block["predictedEvents"]) for block in blocks),
        "perClass": per_class,
    }
    timing_weight = sum(
        int(block["micro"]["tp"])
        for block in blocks
        if "meanAbsoluteTimingErrorMs" in block
    )
    if timing_weight:
        result["meanAbsoluteTimingErrorMs"] = (
            sum(
                float(block.get("meanAbsoluteTimingErrorMs", 0.0))
                * int(block["micro"]["tp"])
                for block in blocks
            )
            / timing_weight
        )
    return result


def _aggregate_taxonomies(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        taxonomy: _aggregate_scores([block[taxonomy] for block in blocks])
        for taxonomy in ("detailed14", "family6", "core3")
    }


def score_suite(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    result_path = output / "benchmark-result.json"
    if result_path.exists():
        raise FileExistsError(result_path)
    competitor_paths = sorted(args.competitor.resolve(strict=True).glob("*.json"))
    if len(competitor_paths) != len(TRACKS):
        raise RuntimeError(
            f"expected {len(TRACKS)} competitor results, found {len(competitor_paths)}"
        )
    per_track = []
    for index, (spec, competitor_path) in enumerate(
        zip(TRACKS, competitor_paths, strict=True)
    ):
        track_root = output / "tracks" / spec.slug
        reference_payload = json.loads(
            (track_root / "reference-events.json").read_text(encoding="utf-8")
        )
        prediction_payload = json.loads(
            (output / "drumscribe" / spec.slug / "predicted-events.json").read_text(
                encoding="utf-8"
            )
        )
        duration = min(WINDOW_SECONDS, sf.info(track_root / "full-mix.wav").duration)
        reference = sorted(
            (float(event["onsetSeconds"]), str(event["instrument"]))
            for event in reference_payload["events"]
            if 0 <= float(event["onsetSeconds"]) < duration
        )
        drumscribe = sorted(
            (float(event["onsetSeconds"]), str(event["instrument"]))
            for event in prediction_payload["rawHits"]
            if 0 <= float(event["onsetSeconds"]) < duration
        )
        drum2notes, competitor_bpm = competitor_events(competitor_path, duration)
        reference_notation = _notation_rows(reference_payload["events"])
        drumscribe_notation = _notation_rows(prediction_payload["events"])
        drum2notes_notation = _competitor_notation(competitor_path, duration)
        tempo_changes = prediction_payload["tempoMap"]["changes"]
        estimated_bpms = [float(change["bpm"]) for change in tempo_changes]
        drumscribe_bpm = statistics.median(estimated_bpms) if estimated_bpms else 0.0
        stem_path = (
            args.demucs_root.resolve(strict=True)
            / "htdemucs_ft"
            / spec.slug
            / "drums.wav"
        )
        per_track.append(
            {
                **asdict(spec),
                "durationSeconds": duration,
                "referenceEvents": len(reference),
                "drumscribeEvents": len(drumscribe),
                "drum2notesEvents": len(drum2notes),
                "eventScores": {
                    "20ms": {
                        "drumscribe": score_taxonomies(reference, drumscribe, 0.020),
                        "drum2notes": score_taxonomies(reference, drum2notes, 0.020),
                    },
                    "50ms": {
                        "drumscribe": score_taxonomies(reference, drumscribe, 0.050),
                        "drum2notes": score_taxonomies(reference, drum2notes, 0.050),
                    },
                },
                "exactNotationScores": {
                    "drumscribe": score_taxonomies(
                        reference_notation, drumscribe_notation, 1e-6
                    ),
                    "drum2notes": score_taxonomies(
                        reference_notation, drum2notes_notation, 1e-6
                    ),
                },
                "tempo": {
                    "referenceBpm": spec.bpm,
                    "drumscribeMedianBpm": drumscribe_bpm,
                    "drumscribeAbsoluteErrorBpm": abs(drumscribe_bpm - spec.bpm),
                    "drum2notesDisplayedBpm": competitor_bpm,
                    "drum2notesAbsoluteErrorBpm": abs(competitor_bpm - spec.bpm),
                },
                "separation": _separation_metrics(
                    track_root / "reference-drums.wav", stem_path
                ),
                "hashes": {
                    "fullMix": _sha256(track_root / "full-mix.wav"),
                    "reference": _sha256(track_root / "reference-events.json"),
                    "drumscribe": _sha256(
                        output / "drumscribe" / spec.slug / "predicted-events.json"
                    ),
                    "drum2notes": _sha256(competitor_path),
                },
            }
        )
        print(json.dumps({"scored": spec.slug}), flush=True)

    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "Ten new rights-cleared original hard-metal full mixes",
            "suiteManifestSha256": _sha256(output / "suite-manifest.json"),
            "status": "sealed_post_freeze_synthetic_full_mix_probe",
            "trackCount": len(TRACKS),
            "totalAudioSeconds": sum(track["durationSeconds"] for track in per_track),
            "referenceFrozenBeforePrediction": True,
            "postTestTuning": False,
            "rightsCleared": True,
            "limitations": [
                "The arrangements are original synthetic hard-metal fixtures, not copyrighted Metallica or Linkin Park recordings.",
                "The drum performances use one licensed acoustic kit and code-generated backing, so this is not a population estimate for released commercial masters.",
                "Demucs and Beat This are local research dependencies with unresolved production checkpoint/training-data licensing in this repository.",
                "Drum2Notes was scored from the structured note data displayed by its public demo result viewer; paid exports were not accessed.",
            ],
        },
        "aggregate": {
            "20ms": {
                "drumscribe": _aggregate_taxonomies(
                    [track["eventScores"]["20ms"]["drumscribe"] for track in per_track]
                ),
                "drum2notes": _aggregate_taxonomies(
                    [track["eventScores"]["20ms"]["drum2notes"] for track in per_track]
                ),
            },
            "50ms": {
                "drumscribe": _aggregate_taxonomies(
                    [track["eventScores"]["50ms"]["drumscribe"] for track in per_track]
                ),
                "drum2notes": _aggregate_taxonomies(
                    [track["eventScores"]["50ms"]["drum2notes"] for track in per_track]
                ),
            },
            "exactNotation": {
                "drumscribe": _aggregate_taxonomies(
                    [track["exactNotationScores"]["drumscribe"] for track in per_track]
                ),
                "drum2notes": _aggregate_taxonomies(
                    [track["exactNotationScores"]["drum2notes"] for track in per_track]
                ),
            },
            "tempoMaeBpm": {
                "drumscribe": statistics.mean(
                    track["tempo"]["drumscribeAbsoluteErrorBpm"] for track in per_track
                ),
                "drum2notes": statistics.mean(
                    track["tempo"]["drum2notesAbsoluteErrorBpm"] for track in per_track
                ),
            },
            "separation": {
                "meanSiSdrDb": statistics.mean(
                    track["separation"]["siSdrDb"] for track in per_track
                ),
                "meanCorrelation": statistics.mean(
                    track["separation"]["correlation"] for track in per_track
                ),
            },
        },
        "tracks": per_track,
    }
    _write_json_new(result_path, report)
    print(json.dumps({"result": str(result_path), "tracks": len(per_track)}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    generate = subcommands.add_parser("generate")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--kit", type=Path, default=KIT_PATH)
    predict = subcommands.add_parser("predict")
    predict.add_argument("--output", type=Path, required=True)
    predict.add_argument("--demucs-root", type=Path, required=True)
    predict.add_argument("--repository", type=Path, default=Path.cwd())
    predict.add_argument("--config", type=Path, default=MODEL_CONFIG)
    predict.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    score = subcommands.add_parser("score")
    score.add_argument("--output", type=Path, required=True)
    score.add_argument("--demucs-root", type=Path, required=True)
    score.add_argument("--competitor", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        generate_suite(args)
    elif args.command == "predict":
        predict_suite(args)
    else:
        score_suite(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
