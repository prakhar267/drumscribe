#!/usr/bin/env python3
"""Run DrumScript on the frozen DrumScribe 100-recording selection and score it.

Run this file with DrumScript's own Python environment and add the DrumScribe
source roots to ``PYTHONPATH``.  DrumScript is intentionally treated as an
unmodified external system; this adapter only normalizes its public event
output to the benchmark taxonomy.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import drumscript

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from run_competitive_drum_benchmark import (
    TOLERANCES,
    combine_event_lists,
    reference_events,
    score_taxonomies,
    sha256,
)

DEFAULT_SELECTION = Path(
    "output/100-track-genre-benchmark-2026-09-03/benchmark-result.json"
)
DEFAULT_PREPARED = Path("data/licensed-corpus/groove-prepared/prepared-dataset.json")
DEFAULT_OUTPUT = Path(
    "output/100-track-genre-benchmark-2026-09-03/drumscript-result.json"
)
DRUMSCRIPT_COMMIT = "59a912be8d5f9866798ead45930b9bf1fd8c9dab"
RUN_MODE = "public detector and standard polyphonic classifier on scored window"
INSTRUMENT_MAP = {
    "kick": "KICK",
    "snare": "SNARE",
    "low_tom": "LOW_TOM",
    "mid_tom": "MID_TOM",
    "high_tom": "HIGH_TOM",
    "hi_hat_closed": "CLOSED_HIHAT",
    "hi_hat_open": "OPEN_HIHAT",
    "crash": "CRASH",
    "ride": "RIDE",
}

Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def resolve(repository: Path, path: Path, *, strict: bool = True) -> Path:
    candidate = path if path.is_absolute() else repository / path
    return candidate.resolve(strict=strict)


def aggregate_scores(
    references: list[list[Event]], predictions: list[list[Event]]
) -> dict[str, Any]:
    combined_reference = combine_event_lists(references)
    combined_prediction = combine_event_lists(predictions)
    return {
        str(int(tolerance * 1000)): score_taxonomies(
            combined_reference, combined_prediction, tolerance
        )
        for tolerance in TOLERANCES
    }


def normalize_events(rows: list[dict[str, Any]], limit: float) -> list[Event]:
    events: list[Event] = []
    for row in rows:
        onset = float(row["time_sec"])
        if not 0 <= onset < limit:
            continue
        for raw_instrument in row.get("instruments", []):
            instrument = INSTRUMENT_MAP.get(str(raw_instrument))
            if instrument:
                events.append((onset, instrument))
    return sorted(events)


def transcribe_detection_window(audio_path: Path, limit: float) -> list[Event]:
    """Run DrumScript's shipped detector/classifier without rendering exports."""
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        audio, sample_rate = drumscript.load_audio(
            str(audio_path), sr=drumscript.SAMPLE_RATE
        )
        sample_count = min(len(audio), round(limit * sample_rate))
        audio = drumscript.normalise_audio(audio[:sample_count])
        onsets = drumscript.detect_onsets(audio, sample_rate)
        rows = drumscript.classify_events(audio, sample_rate, onsets)
    return normalize_events(rows, limit)


def run_prediction_task(task: dict[str, Any]) -> dict[str, Any]:
    sequence = int(task["sequence"])
    audio_path = Path(task["audioPath"])
    raw_path = Path(task["rawPath"])
    audio_hash = str(task["audioSha256"])
    limit = float(task["scoredSeconds"])
    try:
        prediction = transcribe_detection_window(audio_path, limit)
        raw_payload = {
            "schemaVersion": 1,
            "system": "DrumScript",
            "version": "0.2.1",
            "commit": DRUMSCRIPT_COMMIT,
            "mode": RUN_MODE,
            "sourceAudioSha256": audio_hash,
            "scoredSeconds": limit,
            "events": [
                {"onsetSeconds": onset, "instrument": instrument}
                for onset, instrument in prediction
            ],
        }
        raw_path.write_text(
            json.dumps(raw_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {"sequence": sequence, "events": len(prediction), "error": None}
    except Exception as exc:  # noqa: BLE001 - preserve external per-file failures
        return {"sequence": sequence, "events": 0, "error": str(exc)}


def main() -> int:
    args = parse_args()
    repository = args.repository.resolve(strict=True)
    selection_path = resolve(repository, args.selection)
    prepared_path = resolve(repository, args.prepared)
    output_path = resolve(repository, args.output, strict=False)
    raw_root = output_path.parent / "drumscript-raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    if args.workers <= 0:
        raise ValueError("workers must be positive")

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    records_by_hash = {
        str(record["audioSha256"]): record for record in prepared["records"]
    }

    tasks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for selected in selection["tracks"]:
        sequence = int(selected["sequence"])
        audio_hash = str(selected["audioSha256"])
        record = records_by_hash.get(audio_hash)
        if record is None:
            raise RuntimeError(f"prepared dataset has no audio hash {audio_hash}")
        audio_path = Path(record["audioPath"]).resolve(strict=True)
        limit = float(selected["scoredSeconds"])
        raw_path = raw_root / f"{sequence:03d}.json"
        current_mode = None
        if raw_path.exists():
            current_mode = json.loads(raw_path.read_text(encoding="utf-8")).get("mode")
        if current_mode != RUN_MODE:
            tasks.append(
                {
                    "sequence": sequence,
                    "audioPath": str(audio_path),
                    "rawPath": str(raw_path),
                    "audioSha256": audio_hash,
                    "scoredSeconds": limit,
                }
            )

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_prediction_task, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            if result["error"]:
                failures.append(result)
            print(json.dumps(result), flush=True)

    all_reference: list[list[Event]] = []
    all_prediction: list[list[Event]] = []
    grouped_reference: dict[str, list[list[Event]]] = defaultdict(list)
    grouped_prediction: dict[str, list[list[Event]]] = defaultdict(list)
    tracks: list[dict[str, Any]] = []

    for selected in selection["tracks"]:
        sequence = int(selected["sequence"])
        audio_hash = str(selected["audioSha256"])
        record = records_by_hash[audio_hash]
        audio_path = Path(record["audioPath"]).resolve(strict=True)
        annotation_path = Path(record["annotationPath"]).resolve(strict=True)
        limit = float(selected["scoredSeconds"])
        category = str(selected["category"])
        raw_path = raw_root / f"{sequence:03d}.json"
        if raw_path.exists():
            raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))
            prediction = [
                (float(row["onsetSeconds"]), str(row["instrument"]))
                for row in raw_payload["events"]
            ]
        else:
            prediction = []

        reference = reference_events(annotation_path, limit)
        all_reference.append(reference)
        all_prediction.append(prediction)
        grouped_reference[category].append(reference)
        grouped_prediction[category].append(prediction)
        tracks.append(
            {
                "sequence": sequence,
                "audioFile": audio_path.name,
                "audioSha256": audio_hash,
                "style": selected["style"],
                "category": category,
                "scoredSeconds": limit,
                "referenceEventCount": len(reference),
                "predictionEventCount": len(prediction),
                "scores": {
                    str(int(tolerance * 1000)): score_taxonomies(
                        reference, prediction, tolerance
                    )
                    for tolerance in TOLERANCES
                },
            }
        )

    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmarkSelectionSha256": sha256(selection_path),
        "system": {
            "name": "DrumScript",
            "version": "0.2.1",
            "commit": DRUMSCRIPT_COMMIT,
            "mode": (
                "isolated scored window; public detector and default standard "
                "polyphonic classifier; notation rendering skipped"
            ),
            "adapterInstrumentMap": INSTRUMENT_MAP,
        },
        "recordCount": len(tracks),
        "successfulRecordCount": len(tracks) - len(failures),
        "failures": failures,
        "aggregate": aggregate_scores(all_reference, all_prediction),
        "categories": {
            category: {
                "recordCount": len(grouped_reference[category]),
                "scores": aggregate_scores(
                    grouped_reference[category], grouped_prediction[category]
                ),
            }
            for category in selection["categories"]
        },
        "tracks": tracks,
    }
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(output_path),
                "records": len(tracks),
                "failures": len(failures),
                "detailedF1At50ms": report["aggregate"]["50"]["detailed14"]["micro"][
                    "f1"
                ],
                "familyF1At50ms": report["aggregate"]["50"]["family6"]["micro"]["f1"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
