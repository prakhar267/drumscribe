#!/usr/bin/env python3
"""Run Klangio Drum2Notes on the existing 100-recording Groove benchmark.

The public Drum2Notes demo transcribes the first 20 seconds of an upload.  This
runner submits the exact CC BY 4.0 audio files already frozen by
``run_100_track_genre_benchmark.py``, retains every service response, and scores
the returned MusicJSON with the same class-aware event matcher used for
DrumScribe.  The run is resumable and deliberately keeps concurrency low.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from run_100_track_genre_benchmark import CATEGORY_ORDER
from run_competitive_drum_benchmark import (
    TOLERANCES,
    combine_event_lists,
    competitor_events,
    reference_events,
    score_taxonomies,
    sha256,
)

API_ROOT = "https://ai2notes.klang.io/api/Transcription"
DEFAULT_BASELINE = Path(
    "output/100-track-genre-benchmark-2026-09-03/benchmark-result.json"
)
DEFAULT_PREPARED = Path("data/licensed-corpus/groove-prepared/prepared-dataset.json")
DEFAULT_OUTPUT = Path(
    "output/100-track-genre-benchmark-drum2notes-2026-09-05"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=4.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument(
        "--resume-id",
        action="append",
        default=[],
        metavar="SEQUENCE=JOB_ID",
        help="Reuse an already-submitted Drum2Notes job.",
    )
    parser.add_argument(
        "--score-only",
        action="store_true",
        help="Do not submit or poll; score the retained raw results.",
    )
    return parser.parse_args()


def resolve(repository: Path, path: Path, *, strict: bool = True) -> Path:
    candidate = path if path.is_absolute() else repository / path
    return candidate.resolve(strict=strict)


def parse_resume_ids(values: list[str]) -> dict[int, str]:
    result: dict[int, str] = {}
    for value in values:
        sequence_text, separator, job_id = value.partition("=")
        if not separator or not sequence_text.isdigit() or not job_id:
            raise ValueError(f"invalid --resume-id value: {value!r}")
        result[int(sequence_text)] = job_id
    return result


def load_records(
    baseline_path: Path, prepared_path: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    by_track_id = {str(record["trackId"]): record for record in prepared["records"]}
    records: list[dict[str, Any]] = []
    for frozen in baseline["tracks"]:
        track_id = str(frozen["trackId"])
        if track_id not in by_track_id:
            raise RuntimeError(f"missing prepared record for {track_id}")
        prepared_record = by_track_id[track_id]
        audio_path = Path(prepared_record["audioPath"]).resolve(strict=True)
        if sha256(audio_path) != frozen["audioSha256"]:
            raise RuntimeError(f"audio hash changed for {track_id}")
        records.append({**prepared_record, **frozen})
    if len(records) != 100:
        raise RuntimeError(f"expected 100 frozen records; found {len(records)}")
    return baseline, records


def request_json(url: str, *, attempts: int = 4) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "DrumScribe-Benchmark/1.0"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def request_bytes(url: str, *, attempts: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "DrumScribe-Benchmark/1.0"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


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
            "composer": "Google Magenta Groove Dataset",
            "agreedToTerms": True,
        },
    }
    command = [
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
    ]
    completed = subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=150
    )
    payload = json.loads(completed.stdout)
    job_id = str(payload.get("jobId", ""))
    if not job_id:
        raise RuntimeError(f"upload returned no jobId: {payload}")
    return job_id


def poll(job_id: str, poll_seconds: float, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    url = f"{API_ROOT}/get?{urllib.parse.urlencode({'id': job_id})}"
    while True:
        payload = request_json(url)
        state = str(payload.get("state", ""))
        if state in {"ok", "error", "refunded"}:
            return payload
        if time.monotonic() >= deadline:
            return {**payload, "state": "timeout"}
        time.sleep(poll_seconds)


def process_record(
    record: dict[str, Any],
    raw_root: Path,
    poll_seconds: float,
    timeout_seconds: float,
    resume_id: str | None,
) -> dict[str, Any]:
    sequence = int(record["sequence"])
    stem = f"{sequence:03d}"
    job_path = raw_root / f"{stem}.job.json"
    music_path = raw_root / f"{stem}.music.json"
    if job_path.exists():
        retained = json.loads(job_path.read_text(encoding="utf-8"))
        if retained.get("state") == "ok" and music_path.exists():
            return retained
        job_id = str(retained.get("id") or retained.get("jobId") or resume_id or "")
    else:
        job_id = resume_id or ""
    try:
        if not job_id:
            title = f"GMD benchmark {sequence:03d}"
            job_id = submit(Path(record["audioPath"]).resolve(strict=True), title)
            write_json(
                job_path,
                {
                    "id": job_id,
                    "state": "submitted",
                    "sequence": sequence,
                    "sourceAudioSha256": record["audioSha256"],
                },
            )
        payload = poll(job_id, poll_seconds, timeout_seconds)
        retained = {
            **payload,
            "sequence": sequence,
            "sourceAudioSha256": record["audioSha256"],
        }
        write_json(job_path, retained)
        if payload.get("state") == "ok":
            music_url = f"{API_ROOT}/musj?{urllib.parse.urlencode({'id': job_id})}"
            music_path.write_bytes(request_bytes(music_url))
        return retained
    except (
        OSError,
        RuntimeError,
        TimeoutError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        retained = {
            "id": job_id or None,
            "state": "runner_error",
            "sequence": sequence,
            "sourceAudioSha256": record["audioSha256"],
            "runnerError": f"{type(error).__name__}: {error}",
        }
        write_json(job_path, retained)
        return retained


def aggregate_scores(
    references: list[list[tuple[float, str]]],
    predictions: list[list[tuple[float, str]]],
) -> dict[str, Any]:
    combined_reference = combine_event_lists(references)
    combined_prediction = combine_event_lists(predictions)
    return {
        str(int(tolerance * 1000)): score_taxonomies(
            combined_reference, combined_prediction, tolerance
        )
        for tolerance in TOLERANCES
    }


def score_results(
    baseline: dict[str, Any], records: list[dict[str, Any]], output_root: Path
) -> dict[str, Any]:
    raw_root = output_root / "drum2notes-raw"
    drumscribe_root = output_root.parent / "100-track-genre-benchmark-2026-09-03" / "drumscribe-raw"
    all_reference: list[list[tuple[float, str]]] = []
    all_drumscribe: list[list[tuple[float, str]]] = []
    all_competitor: list[list[tuple[float, str]]] = []
    completed_reference: list[list[tuple[float, str]]] = []
    completed_drumscribe: list[list[tuple[float, str]]] = []
    completed_competitor: list[list[tuple[float, str]]] = []
    grouped_reference: dict[str, list[list[tuple[float, str]]]] = defaultdict(list)
    grouped_drumscribe: dict[str, list[list[tuple[float, str]]]] = defaultdict(list)
    grouped_competitor: dict[str, list[list[tuple[float, str]]]] = defaultdict(list)
    completed_grouped_reference: dict[
        str, list[list[tuple[float, str]]]
    ] = defaultdict(list)
    completed_grouped_drumscribe: dict[
        str, list[list[tuple[float, str]]]
    ] = defaultdict(list)
    completed_grouped_competitor: dict[
        str, list[list[tuple[float, str]]]
    ] = defaultdict(list)
    tracks: list[dict[str, Any]] = []
    states: dict[str, int] = defaultdict(int)

    for record in records:
        sequence = int(record["sequence"])
        scored_seconds = float(record["scoredSeconds"])
        reference = reference_events(Path(record["annotationPath"]), scored_seconds)
        drumscribe_payload = json.loads(
            (drumscribe_root / f"{sequence:03d}.json").read_text(encoding="utf-8")
        )
        drumscribe = sorted(
            (float(event["onsetSeconds"]), str(event["instrument"]))
            for event in drumscribe_payload["events"]
            if 0 <= float(event["onsetSeconds"]) < scored_seconds
        )
        job_path = raw_root / f"{sequence:03d}.job.json"
        music_path = raw_root / f"{sequence:03d}.music.json"
        job = (
            json.loads(job_path.read_text(encoding="utf-8"))
            if job_path.exists()
            else {"state": "missing"}
        )
        state = str(job.get("state", "missing"))
        states[state] += 1
        competitor: list[tuple[float, str]] = []
        estimated_bpm: float | None = None
        if state == "ok" and music_path.exists():
            competitor, estimated_bpm = competitor_events(music_path, scored_seconds)

        category = str(record["category"])
        all_reference.append(reference)
        all_drumscribe.append(drumscribe)
        all_competitor.append(competitor)
        grouped_reference[category].append(reference)
        grouped_drumscribe[category].append(drumscribe)
        grouped_competitor[category].append(competitor)
        if state == "ok" and music_path.exists():
            completed_reference.append(reference)
            completed_drumscribe.append(drumscribe)
            completed_competitor.append(competitor)
            completed_grouped_reference[category].append(reference)
            completed_grouped_drumscribe[category].append(drumscribe)
            completed_grouped_competitor[category].append(competitor)
        tracks.append(
            {
                "sequence": sequence,
                "trackId": record["trackId"],
                "audioFile": record["audioFile"],
                "audioSha256": record["audioSha256"],
                "style": record["style"],
                "category": category,
                "scoredSeconds": scored_seconds,
                "drum2notesState": state,
                "drum2notesJobId": job.get("id"),
                "drum2notesEstimatedBpm": estimated_bpm,
                "referenceEventCount": len(reference),
                "drumscribeEventCount": len(drumscribe),
                "drum2notesEventCount": len(competitor),
                "scores": {
                    str(int(tolerance * 1000)): {
                        "drumscribe": score_taxonomies(
                            reference, drumscribe, tolerance
                        ),
                        "drum2notes": score_taxonomies(
                            reference, competitor, tolerance
                        ),
                    }
                    for tolerance in TOLERANCES
                },
            }
        )

    categories = {
        category: {
            "recordCount": len(grouped_reference[category]),
            "drumscribe": aggregate_scores(
                grouped_reference[category], grouped_drumscribe[category]
            ),
            "drum2notes": aggregate_scores(
                grouped_reference[category], grouped_competitor[category]
            ),
        }
        for category in CATEGORY_ORDER
    }
    completed_categories = {
        category: {
            "recordCount": len(completed_grouped_reference[category]),
            "drumscribe": aggregate_scores(
                completed_grouped_reference[category],
                completed_grouped_drumscribe[category],
            ),
            "drum2notes": aggregate_scores(
                completed_grouped_reference[category],
                completed_grouped_competitor[category],
            ),
        }
        for category in CATEGORY_ORDER
        if completed_grouped_reference[category]
    }
    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            **baseline["benchmark"],
            "comparison": "DrumScribe versus Klangio Drum2Notes public 20-second demo",
            "competitorFailurePolicy": (
                "An accepted benchmark item that returned no usable transcription "
                "is retained and scored as zero predicted events."
            ),
            "additionalLimitations": [
                "This remains an isolated electronic-drum detector benchmark, not a full-song source-separation benchmark.",
                "Drum2Notes output is decoded from the audio-aligned MusicJSON used by its public result viewer.",
                "The benchmark test split was opened previously and this repository is not an independent audit environment.",
            ],
        },
        "systems": {
            "drumscribe": baseline["system"],
            "drum2notes": {
                "name": "Klangio Drum2Notes",
                "surface": "live public demo",
                "modelSetting": "solo / all drum notes",
                "resultStates": dict(sorted(states.items())),
            },
        },
        "aggregate": {
            "drumscribe": aggregate_scores(all_reference, all_drumscribe),
            "drum2notes": aggregate_scores(all_reference, all_competitor),
        },
        "categories": categories,
        "completedTranscriptionsOnlyDiagnostic": {
            "recordCount": len(completed_reference),
            "warning": (
                "This excludes service failures and is not the primary all-100 result."
            ),
            "aggregate": {
                "drumscribe": aggregate_scores(
                    completed_reference, completed_drumscribe
                ),
                "drum2notes": aggregate_scores(
                    completed_reference, completed_competitor
                ),
            },
            "categories": completed_categories,
        },
        "tracks": tracks,
    }
    write_json(output_root / "benchmark-result.json", report)
    return report


def main() -> int:
    args = parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("--workers must be between 1 and 4")
    if args.poll_seconds <= 0 or args.timeout_seconds <= 0:
        raise ValueError("poll and timeout values must be positive")

    repository = args.repository.resolve(strict=True)
    baseline_path = resolve(repository, args.baseline)
    prepared_path = resolve(repository, args.prepared)
    output_root = resolve(repository, args.output, strict=False)
    output_root.mkdir(parents=True, exist_ok=True)
    raw_root = output_root / "drum2notes-raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    baseline, records = load_records(baseline_path, prepared_path)

    if not args.score_only:
        resume_ids = parse_resume_ids(args.resume_id)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    process_record,
                    record,
                    raw_root,
                    args.poll_seconds,
                    args.timeout_seconds,
                    resume_ids.get(int(record["sequence"])),
                ): int(record["sequence"])
                for record in records
            }
            for completed, future in enumerate(as_completed(futures), 1):
                result = future.result()
                print(
                    json.dumps(
                        {
                            "completed": completed,
                            "total": len(records),
                            "sequence": futures[future],
                            "state": result.get("state"),
                            "progress": result.get("progress"),
                        }
                    ),
                    flush=True,
                )

    report = score_results(baseline, records, output_root)
    summary = {
        "output": str(output_root / "benchmark-result.json"),
        "states": report["systems"]["drum2notes"]["resultStates"],
        "drumscribeDetailedF1At50ms": report["aggregate"]["drumscribe"]["50"][
            "detailed14"
        ]["micro"]["f1"],
        "drum2notesDetailedF1At50ms": report["aggregate"]["drum2notes"]["50"][
            "detailed14"
        ]["micro"]["f1"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
