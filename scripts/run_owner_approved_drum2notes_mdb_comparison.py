#!/usr/bin/env python3
"""Fresh same-audio comparison of DrumScribe and live Drum2Notes on MDB clips."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPTS_ROOT.parent
for source_root in (
    SCRIPTS_ROOT,
    REPOSITORY_ROOT / "packages" / "music-engine" / "src",
    REPOSITORY_ROOT / "ml" / "src",
):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from drumscribe_music.licensing import require_production_safe
from drumscribe_music.providers.demucs import DemucsAdapter
from drumscribe_music.providers.external import ADTOFResearchTranscriptionProvider
from run_competitive_drum_benchmark import sha256
from run_drum2notes_100_track_benchmark import write_json
from run_drum2notes_mdb_real_benchmark import (
    TRACKS,
    WINDOW_SECONDS,
    drum2notes_events,
    limited,
    process_track,
    scores,
)
from run_mdb_real_benchmark import (
    MDB_INSTRUMENT_TO_FAMILY,
    _combine_event_lists,
    _reference_events,
    score,
)
from run_owner_approved_adtof_mdb import resolve, resolve_executable

APPROVAL_REFERENCE = "OWNER-ATTESTATION-2026-09-05"
DEFAULT_DATASET = Path("data/research-corpus/MDBDrums/MDB Drums")
DEFAULT_SOURCE = Path("output/mdb-real-benchmark-v1")
DEFAULT_OUTPUT = Path("output/mdb-owner-approved-live-rerun-2026-09-05")
DEFAULT_DEMUCS_PYTHON = Path("apps/api/.venv/bin/python")
DEFAULT_ADTOF_PYTHON = Path(".research-models/adtof-env/bin/python")
DEFAULT_ADTOF_RUNNER = Path("scripts/model_runners/adtof_runner.py")
DEFAULT_ADTOF_EXECUTABLE = Path(".research-models/adtof-env/bin/adtof")

Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--demucs-python", type=Path, default=DEFAULT_DEMUCS_PYTHON)
    parser.add_argument("--adtof-python", type=Path, default=DEFAULT_ADTOF_PYTHON)
    parser.add_argument("--adtof-runner", type=Path, default=DEFAULT_ADTOF_RUNNER)
    parser.add_argument(
        "--adtof-executable", type=Path, default=DEFAULT_ADTOF_EXECUTABLE
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--poll-seconds", type=float, default=4.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    return parser.parse_args()


def prediction_events(payload: dict[str, Any]) -> list[Event]:
    result: list[Event] = []
    for hit in payload.get("hits", []):
        family = MDB_INSTRUMENT_TO_FAMILY.get(str(hit.get("instrument", "")))
        onset = float(hit.get("onsetSeconds", -1))
        if family and 0 <= onset < WINDOW_SECONDS:
            result.append((onset, family))
    return sorted(result)


def aggregate(
    references: list[list[Event]], predictions: list[list[Event]]
) -> dict[str, Any]:
    reference = _combine_event_lists(references)
    prediction = _combine_event_lists(predictions)
    return {
        f"{milliseconds}ms": score(reference, prediction, milliseconds / 1_000)
        for milliseconds in (20, 50, 100)
    }


def main() -> int:
    args = parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("--workers must be between 1 and 4")

    repository = args.repository.resolve(strict=True)
    dataset = resolve(repository, args.dataset)
    source_root = resolve(repository, args.source)
    output_root = resolve(repository, args.output, strict=False)
    raw_root = output_root / "drum2notes-raw"
    prediction_root = output_root / "drumscribe-raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    prediction_root.mkdir(parents=True, exist_ok=True)

    # A non-empty output could silently reuse a public-demo job, which would not
    # be a fresh rerun. Refuse it instead of weakening the evidence boundary.
    if any(raw_root.iterdir()) or any(prediction_root.iterdir()):
        raise RuntimeError(f"fresh rerun output is not empty: {output_root}")

    demucs_python = resolve_executable(repository, args.demucs_python)
    adtof_python = resolve_executable(repository, args.adtof_python)
    adtof_runner = resolve(repository, args.adtof_runner)
    adtof_executable = resolve_executable(repository, args.adtof_executable)
    separation = DemucsAdapter(
        model="htdemucs_ft", python_executable=str(demucs_python)
    )
    transcription = ADTOFResearchTranscriptionProvider(
        (
            str(adtof_python),
            str(adtof_runner),
            "--executable",
            str(adtof_executable),
            "--device",
            args.device,
        ),
        model_version="adtof-pytorch-85c192e78f71",
        timeout_seconds=3_600,
    )
    require_production_safe(separation, production=True)
    require_production_safe(transcription, production=True)

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        competitor_futures = {
            executor.submit(
                process_track,
                track,
                source_root,
                raw_root,
                args.poll_seconds,
                args.timeout_seconds,
            ): track
            for track in TRACKS
        }

        for index, track in enumerate(TRACKS, 1):
            clip = source_root / "competitor-upload-20s" / f"{track}_20s.wav"
            with tempfile.TemporaryDirectory(
                prefix="drumscribe-live-comparison-"
            ) as directory:
                stem = Path(directory) / "drums.wav"
                separation.separate_drums(clip, stem)
                stem_hash = sha256(stem)
                hits = transcription.transcribe(stem)
            payload = {
                "schemaVersion": 1,
                "provider": transcription.provider_id,
                "modelVersion": transcription.version,
                "commercialRightsReference": APPROVAL_REFERENCE,
                "source": {
                    "fullMixSha256": sha256(clip),
                    "drumStemSha256": stem_hash,
                    "separationProvider": separation.provider_id,
                    "separationModel": separation.version,
                },
                "hits": [
                    {
                        "instrument": hit.instrument_class.value,
                        "onsetSeconds": hit.onset_seconds,
                        "velocity": hit.velocity,
                        "confidence": hit.confidence,
                    }
                    for hit in hits
                ],
            }
            write_json(prediction_root / f"{track}.json", payload)
            print(
                json.dumps(
                    {
                        "system": "drumscribe",
                        "completed": index,
                        "total": len(TRACKS),
                        "track": track,
                        "hits": len(hits),
                    }
                ),
                flush=True,
            )

        for completed, future in enumerate(as_completed(competitor_futures), 1):
            result = future.result()
            print(
                json.dumps(
                    {
                        "system": "drum2notes",
                        "completed": completed,
                        "total": len(TRACKS),
                        "track": competitor_futures[future],
                        "state": result.get("state"),
                    }
                ),
                flush=True,
            )

    references: list[list[Event]] = []
    drumscribe_predictions: list[list[Event]] = []
    competitor_predictions: list[list[Event]] = []
    rows: list[dict[str, Any]] = []
    states: Counter[str] = Counter()

    for track, genre in TRACKS.items():
        annotation = dataset / "annotations" / "class" / f"{track}_class.txt"
        clip = source_root / "competitor-upload-20s" / f"{track}_20s.wav"
        prediction_path = prediction_root / f"{track}.json"
        job_path = raw_root / f"{track}.job.json"
        music_path = raw_root / f"{track}.music.json"
        prediction_payload = json.loads(prediction_path.read_text(encoding="utf-8"))
        job = json.loads(job_path.read_text(encoding="utf-8"))
        state = str(job.get("state", "missing"))
        states[state] += 1

        reference = limited(_reference_events(annotation))
        drumscribe = prediction_events(prediction_payload)
        competitor: list[Event] = []
        competitor_bpm: float | None = None
        if state == "ok" and music_path.is_file():
            competitor, competitor_bpm = drum2notes_events(music_path)

        references.append(reference)
        drumscribe_predictions.append(drumscribe)
        competitor_predictions.append(competitor)
        rows.append(
            {
                "track": track,
                "genre": genre,
                "drum2notesState": state,
                "drum2notesJobId": job.get("id"),
                "drum2notesEstimatedBpm": competitor_bpm,
                "eventCounts": {
                    "reference": len(reference),
                    "drumscribe": len(drumscribe),
                    "drum2notes": len(competitor),
                },
                "scores": {
                    "drumscribe": scores(reference, drumscribe),
                    "drum2notes": scores(reference, competitor),
                },
                "hashes": {
                    "fullMixExcerpt": sha256(clip),
                    "referenceAnnotation": sha256(annotation),
                    "drumscribePrediction": sha256(prediction_path),
                    "drum2notesRaw": sha256(music_path)
                    if music_path.is_file()
                    else None,
                    "drumStem": prediction_payload["source"]["drumStemSha256"],
                },
            }
        )

    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "MDB same-audio owner-approved live rerun",
            "status": "research_probe_not_sealed",
            "trackCount": len(TRACKS),
            "windowSecondsPerTrack": WINDOW_SECONDS,
            "totalScoredAudioSeconds": len(TRACKS) * WINDOW_SECONDS,
            "inputType": "real human performances in full-band mixtures",
            "referenceSource": "MDB Drums manually reviewed class annotations",
            "datasetLicense": "CC BY-NC-SA 4.0",
            "researchOnly": True,
            "predictionsGeneratedFresh": True,
            "sameAudioBytesForBothSystems": True,
            "matcher": "six-family class-aware one-to-one onset matching",
            "tolerancesMilliseconds": [20, 50, 100],
            "competitorFailurePolicy": (
                "An accepted item with no usable result is retained as zero predictions."
            ),
            "limitations": [
                "Only four predeclared 20-second excerpts are scored.",
                "The MDB MIREX test split was opened previously, so this is not a sealed audit.",
                "MDB is research-only evidence and is not production training material.",
                "Drum2Notes is measured through its live public demo and MusicJSON result.",
            ],
        },
        "systems": {
            "drumscribe": {
                "pipeline": "htdemucs_ft -> ADTOF-pytorch",
                "commercialRightsReference": APPROVAL_REFERENCE,
                "productionProviderGatePassed": True,
            },
            "drum2notes": {
                "product": "Klangio Drum2Notes",
                "surface": "live public demo",
                "resultStates": dict(sorted(states.items())),
            },
        },
        "aggregate": {
            "drumscribe": aggregate(references, drumscribe_predictions),
            "drum2notes": aggregate(references, competitor_predictions),
        },
        "tracks": rows,
        "processingSeconds": round(time.monotonic() - started, 3),
    }
    destination = output_root / "benchmark-result.json"
    write_json(destination, report)
    print(
        json.dumps(
            {
                "output": str(destination),
                "states": report["systems"]["drum2notes"]["resultStates"],
                "f1At50ms": {
                    system: round(result["50ms"]["micro"]["f1"] * 100, 2)
                    for system, result in report["aggregate"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
