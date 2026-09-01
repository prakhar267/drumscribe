#!/usr/bin/env python3
"""Build a leakage-separated synthetic corpus for one licensed acoustic kit."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel
from drumscribe_music import Instrument, TempoMap
from run_sealed_metal_benchmark import _event, _render_drums

SEED = 2_026_090_1
SAMPLE_RATE = 44_100


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _events(index: int) -> tuple[TempoMap, list]:
    rng = np.random.default_rng(SEED + index * 7_919)
    bpm = float(rng.integers(150, 221))
    tempo = TempoMap.constant(bpm, offset_seconds=0.20)
    event_map = {}

    def add(step: int, instrument: Instrument, velocity: int | None = None) -> None:
        beat = Fraction(step, 4)
        event_map[(beat, instrument)] = _event(
            tempo,
            beat,
            instrument,
            int(velocity if velocity is not None else rng.integers(58, 126)),
        )

    steps = 8 * 16
    for step in range(steps):
        position = step % 16
        if position in {0, 4, 8, 12} or rng.random() < 0.27:
            add(step, Instrument.KICK)
        if position in {4, 12} or rng.random() < 0.08:
            add(step, Instrument.SNARE)
        hat_draw = rng.random()
        if step % 2 == 0 and hat_draw < 0.52:
            add(step, Instrument.CLOSED_HIHAT)
        elif step % 2 == 0 and hat_draw < 0.62:
            add(step, Instrument.OPEN_HIHAT)
        elif step % 2 == 1 and hat_draw < 0.72:
            add(step, Instrument.PEDAL_HIHAT)
        cymbal_draw = rng.random()
        if step % 2 == 0 and cymbal_draw < 0.22:
            add(step, Instrument.RIDE)
        elif position in {0, 8} and cymbal_draw < 0.30:
            add(step, Instrument.RIDE_BELL)
        elif position == 0 and cymbal_draw < 0.42:
            add(step, Instrument.CRASH)
        if rng.random() < 0.025:
            add(step, Instrument.TAMBOURINE)
        if rng.random() < 0.012:
            add(step, Instrument.CROSS_STICK)

    # Every recording contains a shuffled full-kit fill so rare classes and
    # overlapping attacks receive natural event-level support.
    toms = (
        Instrument.HIGH_TOM,
        Instrument.MID_TOM,
        Instrument.LOW_TOM,
        Instrument.FLOOR_TOM,
    )
    for measure in range(8):
        start = measure * 16
        fill = [toms[int(index)] for index in rng.permutation(len(toms))]
        for offset, instrument in zip((12, 13, 14, 15), fill, strict=True):
            add(start + offset, instrument)
    guaranteed = (
        Instrument.CROSS_STICK,
        Instrument.OPEN_HIHAT,
        Instrument.PEDAL_HIHAT,
        Instrument.RIDE_BELL,
        Instrument.CRASH,
        Instrument.TAMBOURINE,
    )
    for offset, instrument in enumerate(guaranteed):
        add(2 + offset * 17, instrument)
    return tempo, sorted(
        event_map.values(),
        key=lambda event: (event.onset_seconds, event.instrument.value),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--records", type=int, default=120)
    parser.add_argument("--validation-records", type=int, default=24)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument(
        "--evaluation-only",
        action="store_true",
        help="write every generated record to a sealed synthetic test split",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    if args.records < 1 or args.start_index < 0:
        raise ValueError("records must be positive and start-index cannot be negative")
    if not args.evaluation_only and not 1 <= args.validation_records < args.records:
        raise ValueError("validation records must be between one and total minus one")
    output.mkdir(parents=True)
    kit = args.kit.resolve(strict=True)
    records = []
    class_counts = Counter()
    for position in range(args.records):
        index = args.start_index + position
        tempo, events = _events(index)
        duration = tempo.beat_to_seconds(8 * 4) + 0.9
        audio = _render_drums(events, kit, duration=duration)
        track = f"supported-kit-{index:04d}"
        audio_path = output / "audio" / f"{track}.wav"
        annotation_path = output / "annotations" / f"{track}.json"
        feature_path = output / "features" / f"{track}.npz"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        annotation_path.parent.mkdir(parents=True, exist_ok=True)
        feature_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(audio_path, audio, SAMPLE_RATE, subtype="PCM_24")
        annotation_path.write_text(
            json.dumps(
                {"schemaVersion": 1, "events": [event.as_dict() for event in events]},
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        cache_log_mel(
            audio_path,
            feature_path,
            PreparationConfig(seed=f"supported-kit-{index}", augmentation_variants=0),
        )
        split = (
            "test"
            if args.evaluation_only
            else (
                "validation"
                if position >= args.records - args.validation_records
                else "train"
            )
        )
        records.append(
            {
                "trackId": track,
                "groupId": track,
                "split": split,
                "variant": "original",
                "audioPath": str(audio_path.resolve()),
                "audioSha256": _sha256(audio_path),
                "annotationPath": str(annotation_path.resolve()),
                "featurePath": str(feature_path.resolve()),
                "augmentation": None,
                "durationSeconds": duration,
            }
        )
        class_counts.update(event.instrument.value for event in events)
        if (position + 1) % 10 == 0 or position + 1 == args.records:
            print(f"prepared {position + 1}/{args.records}", flush=True)
    prepared = output / "prepared-dataset.json"
    prepared.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "evaluationOnly": args.evaluation_only,
                "dataset": {
                    "name": "MuldjordKit synthetic full-kit",
                    "version": "1",
                    "sourceType": "synthetic",
                },
                "datasetManifestHash": hashlib.sha256(
                    json.dumps(records, sort_keys=True).encode()
                ).hexdigest(),
                "configuration": {
                    "seed": SEED,
                    "records": args.records,
                    "validationRecords": args.validation_records,
                    "startIndex": args.start_index,
                    "evaluationOnly": args.evaluation_only,
                    "kitPath": str(kit),
                },
                "classCounts": dict(class_counts),
                "records": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"preparedDataset": str(prepared), "classCounts": class_counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
