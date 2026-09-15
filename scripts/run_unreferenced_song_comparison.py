#!/usr/bin/env python3
"""Compare DrumToScore and Drum2Notes on owner-supplied songs without ground truth.

This runner intentionally reports inter-system agreement rather than accuracy.  A
song is only accuracy-scoreable when a trustworthy, time-aligned drum annotation
for the exact recording is available.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import librosa
import numpy as np

REPOSITORY = Path(__file__).resolve().parents[1]
for source_root in (
    REPOSITORY / "scripts",
    REPOSITORY / "packages" / "music-engine" / "src",
):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from drumscribe_music.licensing import require_production_safe
from drumscribe_music.providers.demucs import DemucsAdapter
from drumscribe_music.providers.external import (
    DrumScribeRecallFusionTranscriptionProvider,
)
from run_competitive_drum_benchmark import competitor_events, sha256
from run_drum2notes_100_track_benchmark import API_ROOT, poll, request_bytes, write_json
from run_drum2notes_mdb_real_benchmark import submit
from run_mdb_real_benchmark import INSTRUMENT_TO_FAMILY, score

WINDOW_SECONDS = 20.0
FAMILIES = frozenset(("KICK", "SNARE", "HIHAT", "TOM", "CYMBAL"))
Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, nargs="+")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/owner-download-comparison-2026-09-15"),
    )
    parser.add_argument("--device", choices=("cpu", "mps", "cuda"), default="mps")
    parser.add_argument("--poll-seconds", type=float, default=4.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    return parser.parse_args()


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:80] or "track"


def loudest_window_start(path: Path) -> tuple[float, float]:
    audio, sample_rate = librosa.load(path, sr=8_000, mono=True)
    duration = len(audio) / sample_rate
    if duration <= WINDOW_SECONDS:
        return 0.0, duration
    window = int(WINDOW_SECONDS * sample_rate)
    hop = int(5.0 * sample_rate)
    best_start = 0
    best_rms = -math.inf
    for start in range(0, len(audio) - window + 1, hop):
        chunk = audio[start : start + window]
        rms = float(np.sqrt(np.mean(np.square(chunk), dtype=np.float64)))
        if rms > best_rms:
            best_start, best_rms = start, rms
    return best_start / sample_rate, duration


def extract_clip(source: Path, destination: Path, start: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        (
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-ss",
            f"{start:.6f}",
            "-i",
            str(source),
            "-t",
            str(WINDOW_SECONDS),
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ),
        check=False,
        capture_output=True,
        timeout=180,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace")[-1_000:]
        raise RuntimeError(f"FFmpeg failed for {source}: {detail}")


def family_events(events: list[tuple[float, str]]) -> list[Event]:
    return sorted(
        {
            (round(float(onset), 6), family)
            for onset, instrument in events
            if (family := INSTRUMENT_TO_FAMILY.get(instrument)) in FAMILIES
            and 0 <= float(onset) < WINDOW_SECONDS
        }
    )


def process_competitor(
    clip: Path,
    job_path: Path,
    music_path: Path,
    title: str,
    poll_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    job_id = submit(clip, f"DrumToScore owner comparison - {title}")
    job = poll(job_id, poll_seconds, timeout_seconds)
    retained = {
        **job,
        "id": job_id,
        "sourceAudioSha256": sha256(clip),
    }
    write_json(job_path, retained)
    if job.get("state") == "ok":
        music_path.write_bytes(request_bytes(f"{API_ROOT}/musj?id={job_id}"))
    return retained


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    clip_root = output / "clips"
    stem_root = output / "drum-stems"
    app_root = output / "drumtoscore-raw"
    competitor_root = output / "drum2notes-raw"
    for directory in (clip_root, stem_root, app_root, competitor_root):
        directory.mkdir(parents=True, exist_ok=True)

    transcription = DrumScribeRecallFusionTranscriptionProvider(
        (
            str(REPOSITORY / ".research-models" / "adtof-env" / "bin" / "python"),
            str(
                REPOSITORY / "scripts/model_runners/drumscribe_recall_fusion_runner.py"
            ),
            "--repository",
            str(REPOSITORY),
            "--device",
            args.device,
            "--config",
            str(REPOSITORY / "ml/configs/drumscribe-recall-fusion-v6.json"),
        ),
        model_version="drumscribe-recall-fusion-v6",
        timeout_seconds=3_600,
    )
    separator = DemucsAdapter(
        model="htdemucs_ft",
        python_executable=str(
            REPOSITORY / ".research-models" / "adtof-env" / "bin" / "python"
        ),
    )
    require_production_safe(separator, production=True)
    require_production_safe(transcription, production=True)

    records: list[dict[str, Any]] = []
    for sequence, unresolved in enumerate(args.audio, 1):
        source = unresolved.expanduser().resolve(strict=True)
        track_slug = f"{sequence:02d}-{slug(source.stem)}"
        start, duration = loudest_window_start(source)
        clip = clip_root / f"{track_slug}.wav"
        if not clip.exists():
            extract_clip(source, clip, start)
        records.append(
            {
                "sequence": sequence,
                "title": source.stem,
                "source": source,
                "sourceSha256": sha256(source),
                "durationSeconds": duration,
                "windowStartSeconds": start,
                "clip": clip,
                "clipSha256": sha256(clip),
                "stem": stem_root / f"{track_slug}.wav",
                "app": app_root / f"{track_slug}.json",
                "competitorJob": competitor_root / f"{track_slug}.job.json",
                "competitorMusic": competitor_root / f"{track_slug}.music.json",
            }
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        competitor_futures = {
            record["sequence"]: executor.submit(
                process_competitor,
                record["clip"],
                record["competitorJob"],
                record["competitorMusic"],
                record["title"],
                args.poll_seconds,
                args.timeout_seconds,
            )
            for record in records
        }
        for record in records:
            if not record["stem"].exists():
                separator.separate_drums(record["clip"], record["stem"])
            hits = transcription.transcribe_multiview(record["clip"], record["stem"])
            write_json(
                record["app"],
                {
                    "schemaVersion": 1,
                    "provider": transcription.provider_id,
                    "modelVersion": transcription.version,
                    "sourceAudioSha256": record["clipSha256"],
                    "hits": [
                        {
                            "instrument": hit.instrument_class.value,
                            "onsetSeconds": hit.onset_seconds,
                            "velocity": hit.velocity,
                            "confidence": hit.confidence,
                        }
                        for hit in hits
                    ],
                },
            )
            print(
                json.dumps(
                    {
                        "system": "drumtoscore",
                        "track": record["title"],
                        "hits": len(hits),
                    }
                ),
                flush=True,
            )
        for sequence, future in competitor_futures.items():
            result = future.result()
            print(
                json.dumps(
                    {
                        "system": "drum2notes",
                        "sequence": sequence,
                        "state": result.get("state"),
                    }
                ),
                flush=True,
            )

    rows: list[dict[str, Any]] = []
    for record in records:
        app_payload = json.loads(record["app"].read_text(encoding="utf-8"))
        app_hits = app_payload["hits"]
        app_events = family_events(
            [(float(hit["onsetSeconds"]), str(hit["instrument"])) for hit in app_hits]
        )
        competitor_detailed, competitor_bpm = competitor_events(
            record["competitorMusic"], WINDOW_SECONDS
        )
        competitor = family_events(competitor_detailed)
        rows.append(
            {
                "sequence": record["sequence"],
                "title": record["title"],
                "sourcePath": str(record["source"]),
                "sourceSha256": record["sourceSha256"],
                "sourceDurationSeconds": record["durationSeconds"],
                "windowStartSeconds": record["windowStartSeconds"],
                "windowSeconds": WINDOW_SECONDS,
                "clipSha256": record["clipSha256"],
                "counts": {
                    "drumToScore": len(app_events),
                    "drum2Notes": len(competitor),
                },
                "drumToScoreAverageConfidence": (
                    sum(float(hit["confidence"]) for hit in app_hits) / len(app_hits)
                    if app_hits
                    else 0.0
                ),
                "drum2NotesDisplayedBpm": competitor_bpm,
                "interSystemAgreement": {
                    "50ms": score(competitor, app_events, 0.05),
                    "100ms": score(competitor, app_events, 0.1),
                },
            }
        )

    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "unreferenced_same-audio_product_comparison",
        "systems": {
            "drumToScore": "drumscribe-recall-fusion-v6 after htdemucs_ft",
            "drum2Notes": "Klangio Drum2Notes public 20-second demo",
        },
        "method": {
            "selection": "loudest 20-second RMS window from each owner-supplied file",
            "taxonomy": sorted(FAMILIES),
            "warning": (
                "No authoritative time-aligned notation exists for these exact files. "
                "Agreement and model confidence are not accuracy."
            ),
        },
        "tracks": rows,
    }
    write_json(output / "comparison-result.json", report)
    print(output / "comparison-result.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
