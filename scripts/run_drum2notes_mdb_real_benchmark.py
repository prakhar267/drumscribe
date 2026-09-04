#!/usr/bin/env python3
"""Compare DrumScribe and live Drum2Notes on real full-band MDB recordings.

The four 20-second excerpts and their manually reviewed drum annotations were
predeclared before the competitor run.  MDB Drums is CC BY-NC-SA 4.0, so this
is research-only evidence and must not be presented as a commercial audit.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from run_competitive_drum_benchmark import competitor_events, sha256
from run_drum2notes_100_track_benchmark import API_ROOT, poll, request_bytes, write_json
from run_mdb_real_benchmark import (
    MDB_INSTRUMENT_TO_FAMILY,
    _combine_event_lists,
    _reference_events,
    score,
)

TRACKS = {
    "MusicDelta_Country1": "country",
    "MusicDelta_FreeJazz": "free jazz",
    "MusicDelta_Grunge": "grunge",
    "MusicDelta_SpeedMetal": "speed metal",
}
WINDOW_SECONDS = 20.0
TOLERANCES_MS = (20, 50, 100)
DEFAULT_DATASET = Path("data/research-corpus/MDBDrums/MDB Drums")
DEFAULT_SOURCE = Path("output/mdb-real-benchmark-v1")
DEFAULT_OUTPUT = Path("output/mdb-real-live-comparison-2026-09-05")

Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--poll-seconds", type=float, default=4.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--score-only", action="store_true")
    return parser.parse_args()


def resolve(repository: Path, path: Path, *, strict: bool = True) -> Path:
    candidate = path if path.is_absolute() else repository / path
    return candidate.resolve(strict=strict)


def submit(audio_path: Path, title: str) -> str:
    params = {
        "settings": {
            "instruments": ["drums"],
            "min_duration": 0.0625,
            "triplets": True,
            "sections": False,
            "model": "solo",
            "drums": {"drum_notes": "all"},
        },
        "apriori": {
            "title": title,
            "composer": "MusicDelta / MedleyDB",
            "agreedToTerms": True,
        },
    }
    completed = subprocess.run(
        [
            "curl",
            "-fsS",
            "--retry",
            "3",
            "--retry-all-errors",
            "--max-time",
            "120",
            "-X",
            "POST",
            f"{API_ROOT}/upload",
            "-F",
            f"file=@{audio_path}",
            "--form-string",
            "usecredits=false",
            "--form-string",
            "usetickets=false",
            "--form-string",
            "source=file",
            "--form-string",
            "type=drum2notes",
            "--form-string",
            f"params={json.dumps(params, separators=(',', ':'))}",
            "--form-string",
            f"title={title}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=150,
    )
    payload = json.loads(completed.stdout)
    job_id = str(payload.get("jobId", ""))
    if not job_id:
        raise RuntimeError(f"upload returned no jobId: {payload}")
    return job_id


def process_track(
    track: str,
    source_root: Path,
    raw_root: Path,
    poll_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    job_path = raw_root / f"{track}.job.json"
    music_path = raw_root / f"{track}.music.json"
    if job_path.exists():
        retained = json.loads(job_path.read_text(encoding="utf-8"))
        if retained.get("state") == "ok" and music_path.exists():
            return retained
        job_id = str(retained.get("id") or retained.get("jobId") or "")
    else:
        job_id = ""
    clip = source_root / "competitor-upload-20s" / f"{track}_20s.wav"
    try:
        if not job_id:
            job_id = submit(clip, f"MDB real benchmark - {track}")
            write_json(
                job_path,
                {
                    "id": job_id,
                    "state": "submitted",
                    "track": track,
                    "sourceAudioSha256": sha256(clip),
                },
            )
        payload = poll(job_id, poll_seconds, timeout_seconds)
        retained = {
            **payload,
            "id": job_id,
            "track": track,
            "sourceAudioSha256": sha256(clip),
        }
        write_json(job_path, retained)
        if payload.get("state") == "ok":
            music_path.write_bytes(request_bytes(f"{API_ROOT}/musj?id={job_id}"))
        return retained
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        retained = {
            "id": job_id or None,
            "state": "runner_error",
            "track": track,
            "sourceAudioSha256": sha256(clip),
            "runnerError": f"{type(error).__name__}: {error}",
        }
        write_json(job_path, retained)
        return retained


def limited(events: list[Event]) -> list[Event]:
    return [(time, label) for time, label in events if 0 <= time < WINDOW_SECONDS]


def drumscribe_events(path: Path) -> list[Event]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: list[Event] = []
    for hit in payload.get("hits", []):
        family = MDB_INSTRUMENT_TO_FAMILY.get(str(hit.get("instrument", "")))
        onset = float(hit.get("onsetSeconds", -1))
        if family and 0 <= onset < WINDOW_SECONDS:
            result.append((onset, family))
    return sorted(result)


def drum2notes_events(path: Path) -> tuple[list[Event], float]:
    detailed, bpm = competitor_events(path, WINDOW_SECONDS)
    return sorted(
        (time, MDB_INSTRUMENT_TO_FAMILY[instrument])
        for time, instrument in detailed
        if instrument in MDB_INSTRUMENT_TO_FAMILY
    ), bpm


def scores(reference: list[Event], prediction: list[Event]) -> dict[str, Any]:
    return {
        f"{milliseconds}ms": score(reference, prediction, milliseconds / 1000)
        for milliseconds in TOLERANCES_MS
    }


def aggregate(
    references: list[list[Event]], predictions: list[list[Event]]
) -> dict[str, Any]:
    return scores(_combine_event_lists(references), _combine_event_lists(predictions))


def build_report(dataset: Path, source_root: Path, output_root: Path) -> dict[str, Any]:
    raw_root = output_root / "drum2notes-raw"
    references: list[list[Event]] = []
    app_predictions: list[list[Event]] = []
    research_predictions: list[list[Event]] = []
    competitor_predictions: list[list[Event]] = []
    rows: list[dict[str, Any]] = []
    states: Counter[str] = Counter()

    for track, genre in TRACKS.items():
        annotation = dataset / "annotations" / "class" / f"{track}_class.txt"
        clip = source_root / "competitor-upload-20s" / f"{track}_20s.wav"
        app_path = output_root / "drumscribe-hybrid-raw" / f"{track}.json"
        research_path = output_root / "drumscribe-research-raw" / f"{track}.json"
        separated_stem = (
            output_root
            / "same-input-demucs"
            / "htdemucs_ft"
            / f"{track}_20s"
            / "drums.wav"
        )
        job_path = raw_root / f"{track}.job.json"
        music_path = raw_root / f"{track}.music.json"

        reference = limited(_reference_events(annotation))
        app = drumscribe_events(app_path)
        research = drumscribe_events(research_path)
        job = (
            json.loads(job_path.read_text(encoding="utf-8"))
            if job_path.exists()
            else {"state": "missing"}
        )
        state = str(job.get("state", "missing"))
        states[state] += 1
        competitor: list[Event] = []
        competitor_bpm: float | None = None
        if state == "ok" and music_path.exists():
            competitor, competitor_bpm = drum2notes_events(music_path)

        references.append(reference)
        app_predictions.append(app)
        research_predictions.append(research)
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
                    "drumscribeCurrentApp": len(app),
                    "drumscribeResearchBest": len(research),
                    "drum2notes": len(competitor),
                },
                "scores": {
                    "drumscribeCurrentApp": scores(reference, app),
                    "drumscribeResearchBest": scores(reference, research),
                    "drum2notes": scores(reference, competitor),
                },
                "hashes": {
                    "fullMixExcerpt": sha256(clip),
                    "sharedSeparatedDrumStem": sha256(separated_stem),
                    "referenceAnnotation": sha256(annotation),
                    "drumscribeCurrentAppPrediction": sha256(app_path),
                    "drumscribeResearchPrediction": sha256(research_path),
                    "drum2notesRaw": sha256(music_path)
                    if music_path.exists()
                    else None,
                },
            }
        )

    return {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "MDB Drums real full-mixture live comparison",
            "status": "research_probe_not_sealed",
            "trackCount": len(TRACKS),
            "windowSecondsPerTrack": WINDOW_SECONDS,
            "totalScoredAudioSeconds": len(TRACKS) * WINDOW_SECONDS,
            "inputType": "real human performances in full-band mixtures",
            "referenceSource": "MDB Drums manually reviewed class annotations",
            "datasetLicense": "CC BY-NC-SA 4.0",
            "researchOnly": True,
            "matcher": "class-aware one-to-one onset matching",
            "tolerancesMilliseconds": list(TOLERANCES_MS),
            "competitorFailurePolicy": (
                "An accepted item with no usable result is retained as zero predictions."
            ),
            "limitations": [
                "Only four predeclared 20-second excerpts are scored; this is not a market-wide accuracy claim.",
                "The MDB MIREX test split was opened during prior development, so this is not a fresh sealed test.",
                "The current app path and best research path both use htdemucs_ft stems; its commercial checkpoint rights remain unresolved.",
                "The best research path additionally uses non-commercial ADTOF and cannot be shipped in a paid product.",
                "Drum2Notes is measured through its live public 20-second demo and audio-aligned MusicJSON result.",
            ],
        },
        "systems": {
            "drumscribeCurrentApp": {
                "pipeline": "htdemucs_ft -> drumscribe-hybrid-v1",
                "status": "application-integrated research beta; not production-approved",
            },
            "drumscribeResearchBest": {
                "pipeline": "htdemucs_ft -> ADTOF",
                "status": "non-commercial research only",
            },
            "drum2notes": {
                "product": "Klangio Drum2Notes",
                "surface": "live public demo",
                "resultStates": dict(sorted(states.items())),
            },
        },
        "aggregate": {
            "drumscribeCurrentApp": aggregate(references, app_predictions),
            "drumscribeResearchBest": aggregate(references, research_predictions),
            "drum2notes": aggregate(references, competitor_predictions),
        },
        "tracks": rows,
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
    raw_root.mkdir(parents=True, exist_ok=True)

    if not args.score_only:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
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
            for completed, future in enumerate(as_completed(futures), 1):
                result = future.result()
                print(
                    json.dumps(
                        {
                            "completed": completed,
                            "total": len(TRACKS),
                            "track": futures[future],
                            "state": result.get("state"),
                            "progress": result.get("progress"),
                        }
                    ),
                    flush=True,
                )

    report = build_report(dataset, source_root, output_root)
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
