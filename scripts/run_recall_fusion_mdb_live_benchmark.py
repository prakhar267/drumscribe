#!/usr/bin/env python3
"""Rerun production DrumScribe v3 and live Drum2Notes on 11 MDB mixtures.

MDB Drums is CC BY-NC-SA 4.0, so this is research-only evaluation evidence.
The test partition was opened in earlier development and is not a sealed audit.
"""

from __future__ import annotations

import argparse
import json
import sys
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
from drumscribe_music.providers.external import (
    DrumScribeRecallFusionTranscriptionProvider,
)
from run_competitive_drum_benchmark import sha256
from run_drum2notes_100_track_benchmark import write_json
from run_drum2notes_mdb_real_benchmark import (
    WINDOW_SECONDS,
    drum2notes_events,
    limited,
    process_track,
    scores,
)
from run_mdb_real_benchmark import (
    MDB_INSTRUMENT_TO_FAMILY,
    TEST_TRACKS,
    _combine_event_lists,
    _reference_events,
    score,
)
from run_owner_approved_adtof_mdb import resolve, resolve_executable
from run_owner_approved_drum2notes_mdb_comparison import (
    APPROVAL_REFERENCE,
    TEST_GENRES,
    wav_duration_seconds,
)

DEFAULT_DATASET = Path("data/research-corpus/MDBDrums/MDB Drums")
DEFAULT_SOURCE = Path("output/mdb-real-test11-inputs")
DEFAULT_OUTPUT = Path("output/mdb-recall-fusion-v3-live-test11-2026-09-06")
DEFAULT_DEMUCS_PYTHON = Path("apps/api/.venv/bin/python")
DEFAULT_ADTOF_PYTHON = Path(".research-models/adtof-env/bin/python")
DEFAULT_RECALL_FUSION_RUNNER = Path(
    "scripts/model_runners/drumscribe_recall_fusion_runner.py"
)
MODEL_VERSION = "drumscribe-recall-fusion-v3"
Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--demucs-python", type=Path, default=DEFAULT_DEMUCS_PYTHON)
    parser.add_argument("--adtof-python", type=Path, default=DEFAULT_ADTOF_PYTHON)
    parser.add_argument(
        "--recall-fusion-runner", type=Path, default=DEFAULT_RECALL_FUSION_RUNNER
    )
    parser.add_argument("--device", choices=("cpu", "cuda", "mps"), default="cpu")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=4.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--score-only", action="store_true")
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


def run_predictions(
    repository: Path,
    source_root: Path,
    output_root: Path,
    args: argparse.Namespace,
) -> None:
    competitor_root = output_root / "drum2notes-raw"
    prediction_root = output_root / "drumscribe-raw"
    stem_root = output_root / "drum-stems"
    competitor_root.mkdir(parents=True, exist_ok=True)
    prediction_root.mkdir(parents=True, exist_ok=True)
    stem_root.mkdir(parents=True, exist_ok=True)
    if any(competitor_root.iterdir()) or any(prediction_root.iterdir()):
        raise RuntimeError(f"fresh rerun output is not empty: {output_root}")

    adtof_python = resolve_executable(repository, args.adtof_python)
    runner = resolve(repository, args.recall_fusion_runner)
    transcription = DrumScribeRecallFusionTranscriptionProvider(
        (
            str(adtof_python),
            str(runner),
            "--repository",
            str(repository),
            "--device",
            args.device,
        ),
        model_version=MODEL_VERSION,
        timeout_seconds=3_600,
    )
    separation = DemucsAdapter(
        model="htdemucs_ft",
        python_executable=str(resolve_executable(repository, args.demucs_python)),
    )
    require_production_safe(transcription, production=True)
    require_production_safe(separation, production=True)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_track,
                track,
                source_root,
                competitor_root,
                args.poll_seconds,
                args.timeout_seconds,
            ): track
            for track in TEST_TRACKS
        }

        for completed, track in enumerate(TEST_TRACKS, 1):
            clip = source_root / "competitor-upload-20s" / f"{track}_20s.wav"
            stem = stem_root / f"{track}_drums.wav"
            separation.separate_drums(clip, stem)
            hits = transcription.transcribe_multiview(clip, stem)
            payload = {
                "schemaVersion": 1,
                "provider": transcription.provider_id,
                "modelVersion": transcription.version,
                "decoder": MODEL_VERSION,
                "commercialRightsReference": APPROVAL_REFERENCE,
                "source": {
                    "fullMixSha256": sha256(clip),
                    "drumStemSha256": sha256(stem),
                    "separationProvider": separation.provider_id,
                    "separationModel": separation.version,
                    "sameFullMixSubmittedToCompetitor": True,
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
                        "completed": completed,
                        "total": len(TEST_TRACKS),
                        "track": track,
                        "hits": len(hits),
                    }
                ),
                flush=True,
            )

        for completed, future in enumerate(as_completed(futures), 1):
            result = future.result()
            print(
                json.dumps(
                    {
                        "system": "drum2notes",
                        "completed": completed,
                        "total": len(TEST_TRACKS),
                        "track": futures[future],
                        "state": result.get("state"),
                    }
                ),
                flush=True,
            )


def build_report(
    dataset: Path,
    source_root: Path,
    output_root: Path,
    processing_seconds: float | None,
) -> dict[str, Any]:
    references: list[list[Event]] = []
    drumscribe_predictions: list[list[Event]] = []
    competitor_predictions: list[list[Event]] = []
    tracks: list[dict[str, Any]] = []
    states: Counter[str] = Counter()

    for track in TEST_TRACKS:
        annotation = dataset / "annotations" / "class" / f"{track}_class.txt"
        clip = source_root / "competitor-upload-20s" / f"{track}_20s.wav"
        stem = output_root / "drum-stems" / f"{track}_drums.wav"
        prediction_path = output_root / "drumscribe-raw" / f"{track}.json"
        job_path = output_root / "drum2notes-raw" / f"{track}.job.json"
        music_path = output_root / "drum2notes-raw" / f"{track}.music.json"
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
        tracks.append(
            {
                "track": track,
                "genre": TEST_GENRES[track],
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
                    "drumStem": sha256(stem),
                    "drumscribePrediction": sha256(prediction_path),
                    "drum2notesRaw": sha256(music_path)
                    if music_path.is_file()
                    else None,
                },
            }
        )

    total_audio_seconds = sum(
        wav_duration_seconds(
            source_root / "competitor-upload-20s" / f"{track}_20s.wav"
        )
        for track in TEST_TRACKS
    )
    return {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "MDB real full-mixture production-v3 live comparison",
            "status": "opened_development_same_audio_live_comparison",
            "trackCount": len(TEST_TRACKS),
            "windowSecondsPerTrack": WINDOW_SECONDS,
            "totalScoredAudioSeconds": round(total_audio_seconds, 6),
            "inputType": "real human performances in full-band mixtures",
            "referenceSource": "MDB Drums manually reviewed class annotations",
            "datasetLicense": "CC BY-NC-SA 4.0",
            "researchOnly": True,
            "predictionsGeneratedFresh": True,
            "sameAudioBytesForBothSystems": True,
            "primaryMetric": "six-family class-aware micro F1 at 50ms",
            "matcher": "six-family class-aware one-to-one onset matching",
            "tolerancesMilliseconds": [20, 50, 100],
            "competitorFailurePolicy": (
                "An accepted item with no usable result is retained as zero predictions."
            ),
            "limitations": [
                "The 11-track MDB MIREX test partition was opened during earlier development; this is not a sealed or independent audit.",
                "Only the first 20 seconds of each track are scored.",
                "MDB is research-only evidence and is not production training material.",
                "Drum2Notes is measured through its live public demo and MusicJSON result.",
                "A result on this corpus does not establish universal accuracy across commercial songs.",
            ],
        },
        "systems": {
            "drumscribe": {
                "pipeline": (
                    "htdemucs_ft + guarded direct/stem activation fusion + "
                    "first-party articulation recovery"
                ),
                "provider": MODEL_VERSION,
                "modelVersion": MODEL_VERSION,
                "commercialRightsReference": APPROVAL_REFERENCE,
                "productionProviderGatePassed": True,
            },
            "drum2notes": {
                "product": "Klangio Drum2Notes",
                "surface": "live public demo",
                "modelSetting": "solo / all drum notes",
                "resultStates": dict(sorted(states.items())),
            },
        },
        "aggregate": {
            "drumscribe": aggregate(references, drumscribe_predictions),
            "drum2notes": aggregate(references, competitor_predictions),
        },
        "tracks": tracks,
        "processingSeconds": (
            round(processing_seconds, 3) if processing_seconds is not None else None
        ),
    }


def main() -> int:
    args = parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("--workers must be between 1 and 4")
    repository = args.repository.resolve(strict=True)
    dataset = resolve(repository, args.dataset)
    source_root = resolve(repository, args.source)
    output_root = resolve(repository, args.output, strict=False)
    output_root.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    if not args.score_only:
        run_predictions(repository, source_root, output_root, args)
    report = build_report(
        dataset,
        source_root,
        output_root,
        None if args.score_only else time.monotonic() - started,
    )
    destination = output_root / "benchmark-result.json"
    if destination.exists() and not args.score_only:
        raise FileExistsError(destination)
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
