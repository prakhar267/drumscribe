#!/usr/bin/env python3
"""Run a sealed, rights-cleared full-mix launch check on two real performances.

The benchmark combines previously unselected real human Groove MIDI Dataset drum
performances (with aligned MIDI-derived ground truth) with licensed musical
backing. The result is a constructed full mixture, not an untouched released
song. Selection is frozen and hashed before inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
for root in (
    REPOSITORY / "scripts",
    REPOSITORY / "ml" / "src",
    REPOSITORY / "packages" / "music-engine" / "src",
):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from drumscribe_music.providers.demucs import DemucsAdapter
from drumscribe_music.providers.external import (
    DrumScribeRecallFusionTranscriptionProvider,
)
from run_competitive_drum_benchmark import combine_event_lists, reference_events
from run_mdb_real_benchmark import score

CASES = (
    {
        "id": "rock-groove8-65",
        "trackId": "drummer1/eval_session/8",
        "style": "rock-groove8",
        "seconds": 45.0,
        "backing": "data/rights-cleared-test-audio/big-rock-test-45s.mp3",
        "backingDrumEstimate": (
            "data/rights-cleared-test-audio/demucs-output/htdemucs/"
            "big-rock-test-45s/drums.wav"
        ),
        "backingLicense": "Kevin MacLeod, Big Rock, CC BY 3.0",
    },
    {
        "id": "funk-108",
        "trackId": "drummer8/session1/19",
        "style": "funk",
        "seconds": 60.0,
        "backing": "data/rights-cleared-test-audio/change-my-mind-test-75s.mp3",
        "backingDrumEstimate": (
            "data/rights-cleared-test-audio/demucs-output/htdemucs/"
            "change-my-mind-test-75s/drums.wav"
        ),
        "backingLicense": "US Air Force Band, Change My Mind, public domain",
    },
)

FAMILY5 = {
    "KICK": "KICK",
    "SNARE": "SNARE",
    "CROSS_STICK": "SNARE",
    "HIGH_TOM": "TOM",
    "MID_TOM": "TOM",
    "LOW_TOM": "TOM",
    "FLOOR_TOM": "TOM",
    "CLOSED_HIHAT": "HIHAT",
    "OPEN_HIHAT": "HIHAT",
    "PEDAL_HIHAT": "HIHAT",
    "CRASH": "CYMBAL",
    "RIDE": "CYMBAL",
    "RIDE_BELL": "CYMBAL",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def ffmpeg(*arguments: str) -> None:
    subprocess.run(
        ("ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *arguments),
        check=True,
        timeout=600,
    )


def mean_volume(path: Path, seconds: float) -> float:
    completed = subprocess.run(
        (
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-t",
            str(seconds),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", completed.stderr)
    if not match:
        raise RuntimeError(f"ffmpeg did not report mean volume for {path}")
    return float(match.group(1))


def make_mix(
    *,
    drums: Path,
    backing: Path,
    backing_drums: Path,
    seconds: float,
    instrumental: Path,
    mixture: Path,
) -> dict[str, float]:
    # Remove the prior learned drum estimate from the licensed song, then place
    # the separately recorded human performance into that backing.
    ffmpeg(
        "-y",
        "-i",
        str(backing),
        "-i",
        str(backing_drums),
        "-filter_complex",
        "[0:a][1:a]amix=inputs=2:weights='1 -1':normalize=0,alimiter=limit=0.95[a]",
        "-map",
        "[a]",
        "-t",
        str(seconds),
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(instrumental),
    )
    drum_mean = mean_volume(drums, seconds)
    backing_mean = mean_volume(instrumental, seconds)
    drum_gain = 10 ** ((-20.0 - drum_mean) / 20.0)
    backing_gain = 10 ** ((-23.0 - backing_mean) / 20.0)
    ffmpeg(
        "-y",
        "-i",
        str(drums),
        "-i",
        str(instrumental),
        "-filter_complex",
        (
            "[0:a][1:a]amix=inputs=2:"
            f"weights='{drum_gain:.8f} {backing_gain:.8f}':"
            "normalize=0,alimiter=limit=0.95[a]"
        ),
        "-map",
        "[a]",
        "-t",
        str(seconds),
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(mixture),
    )
    return {
        "sourceDrumMeanDb": drum_mean,
        "backingMeanDb": backing_mean,
        "drumLinearGain": drum_gain,
        "backingLinearGain": backing_gain,
        "targetDrumMeanDb": -20.0,
        "targetBackingMeanDb": -23.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/launch-rights-cleared-fullmix-v2-2026-09-12"),
    )
    parser.add_argument("--device", choices=("cpu", "mps", "cuda"), default="mps")
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else REPOSITORY / args.output
    if output.exists():
        raise RuntimeError(f"refusing to overwrite sealed benchmark: {output}")
    output.mkdir(parents=True)

    prepared = json.loads(
        (
            REPOSITORY / "data/licensed-corpus/groove-prepared/prepared-dataset.json"
        ).read_text(encoding="utf-8")
    )
    by_id = {str(item["trackId"]): item for item in prepared["records"]}
    items: list[dict[str, Any]] = []
    for case in CASES:
        record = by_id[str(case["trackId"])]
        if record["split"] != "test" or float(record["durationSeconds"]) < float(
            case["seconds"]
        ):
            raise RuntimeError(f"invalid sealed source selection: {case['trackId']}")
        drums = Path(record["audioPath"]).resolve(strict=True)
        annotation = Path(record["annotationPath"]).resolve(strict=True)
        backing = (REPOSITORY / str(case["backing"])).resolve(strict=True)
        backing_drums = (REPOSITORY / str(case["backingDrumEstimate"])).resolve(
            strict=True
        )
        items.append(
            {
                **case,
                "sourceSplit": "test",
                "sourceDrumAudio": str(drums),
                "sourceDrumAudioSha256": sha256(drums),
                "referenceAnnotation": str(annotation),
                "referenceAnnotationSha256": sha256(annotation),
                "backing": str(backing),
                "backingSha256": sha256(backing),
                "backingDrumEstimate": str(backing_drums),
                "backingDrumEstimateSha256": sha256(backing_drums),
            }
        )

    manifest = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmarkId": "launch-rights-cleared-fullmix-v2-2026-09-12",
        "selectionFrozenBeforeInference": True,
        "inputDescription": (
            "Constructed full mixtures: previously unselected real human GMD drums "
            "plus licensed song backing with a prior learned drum estimate removed."
        ),
        "limitations": [
            "These are constructed rights-cleared mixtures, not untouched released songs.",
            "Residual percussion can remain in the learned backing subtraction.",
            "The GMD test split and model family are known to the organization, but these exact source performances were absent from prior benchmark manifests before selection.",
        ],
        "items": items,
    }
    manifest_path = output / "selection-manifest.json"
    write_json(manifest_path, manifest)

    separator = DemucsAdapter(
        model="htdemucs_ft",
        python_executable=str(REPOSITORY / "apps/api/.venv/bin/python"),
    )
    transcription = DrumScribeRecallFusionTranscriptionProvider(
        (
            str(REPOSITORY / ".research-models/adtof-env/bin/python"),
            str(
                REPOSITORY / "scripts/model_runners/drumscribe_recall_fusion_runner.py"
            ),
            "--repository",
            str(REPOSITORY),
            "--device",
            args.device,
        ),
        model_version="drumscribe-recall-fusion-v6",
        timeout_seconds=3_600,
    )

    track_results: list[dict[str, Any]] = []
    references: list[list[tuple[float, str]]] = []
    predictions: list[list[tuple[float, str]]] = []
    isolated_control_predictions: list[list[tuple[float, str]]] = []
    for item in items:
        case_root = output / str(item["id"])
        case_root.mkdir()
        instrumental = case_root / "licensed-backing-no-drums.wav"
        mixture = case_root / "full-mix.wav"
        stem = case_root / "separated-drums.wav"
        started = time.monotonic()
        mix_levels = make_mix(
            drums=Path(item["sourceDrumAudio"]),
            backing=Path(item["backing"]),
            backing_drums=Path(item["backingDrumEstimate"]),
            seconds=float(item["seconds"]),
            instrumental=instrumental,
            mixture=mixture,
        )
        separation_started = time.monotonic()
        separator.separate_drums(mixture, stem)
        separation_seconds = time.monotonic() - separation_started
        transcription_started = time.monotonic()
        hits = transcription.transcribe_multiview(mixture, stem)
        transcription_seconds = time.monotonic() - transcription_started
        isolated_control_started = time.monotonic()
        isolated_control_hits = transcription.transcribe(Path(item["sourceDrumAudio"]))
        isolated_control_seconds = time.monotonic() - isolated_control_started

        reference_detailed = reference_events(
            Path(item["referenceAnnotation"]), float(item["seconds"])
        )
        prediction_detailed = sorted(
            (hit.onset_seconds, hit.instrument_class.value)
            for hit in hits
            if hit.onset_seconds < float(item["seconds"])
        )
        reference = sorted(
            (onset, FAMILY5[instrument])
            for onset, instrument in reference_detailed
            if instrument in FAMILY5
        )
        prediction = sorted(
            (onset, FAMILY5[instrument])
            for onset, instrument in prediction_detailed
            if instrument in FAMILY5
        )
        isolated_control_detailed = sorted(
            (hit.onset_seconds, hit.instrument_class.value)
            for hit in isolated_control_hits
            if hit.onset_seconds < float(item["seconds"])
        )
        isolated_control = sorted(
            (onset, FAMILY5[instrument])
            for onset, instrument in isolated_control_detailed
            if instrument in FAMILY5
        )
        references.append(reference)
        predictions.append(prediction)
        isolated_control_predictions.append(isolated_control)
        scores = {
            f"{milliseconds}ms": score(reference, prediction, milliseconds / 1_000)
            for milliseconds in (20, 50, 100)
        }
        raw_path = case_root / "prediction.json"
        write_json(
            raw_path,
            {
                "schemaVersion": 1,
                "provider": transcription.provider_id,
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
        isolated_control_path = case_root / "isolated-drum-control-prediction.json"
        write_json(
            isolated_control_path,
            {
                "schemaVersion": 1,
                "provider": transcription.provider_id,
                "hits": [
                    {
                        "instrument": hit.instrument_class.value,
                        "onsetSeconds": hit.onset_seconds,
                        "velocity": hit.velocity,
                        "confidence": hit.confidence,
                    }
                    for hit in isolated_control_hits
                ],
            },
        )
        track_results.append(
            {
                "id": item["id"],
                "trackId": item["trackId"],
                "style": item["style"],
                "seconds": item["seconds"],
                "eventCounts": {
                    "reference": len(reference),
                    "prediction": len(prediction),
                },
                "family5Scores": scores,
                "detailedArticulationScores": {
                    f"{milliseconds}ms": score(
                        reference_detailed,
                        prediction_detailed,
                        milliseconds / 1_000,
                    )
                    for milliseconds in (20, 50, 100)
                },
                "isolatedDrumControlScores": {
                    f"{milliseconds}ms": score(
                        reference,
                        isolated_control,
                        milliseconds / 1_000,
                    )
                    for milliseconds in (20, 50, 100)
                },
                "isolatedDrumDetailedControlScores": {
                    f"{milliseconds}ms": score(
                        reference_detailed,
                        isolated_control_detailed,
                        milliseconds / 1_000,
                    )
                    for milliseconds in (20, 50, 100)
                },
                "runtimeSeconds": {
                    "separation": round(separation_seconds, 3),
                    "transcription": round(transcription_seconds, 3),
                    "isolatedDrumControl": round(isolated_control_seconds, 3),
                    "total": round(time.monotonic() - started, 3),
                },
                "mixLevelCalibration": mix_levels,
                "hashes": {
                    "mixture": sha256(mixture),
                    "separatedDrums": sha256(stem),
                    "prediction": sha256(raw_path),
                    "isolatedDrumControlPrediction": sha256(isolated_control_path),
                },
            }
        )
        print(
            json.dumps(
                {"completed": item["id"], "f1At50ms": scores["50ms"]["micro"]["f1"]}
            )
        )

    combined_reference = combine_event_lists(references)
    combined_prediction = combine_event_lists(predictions)
    combined_isolated_control = combine_event_lists(isolated_control_predictions)
    aggregate = {
        f"{milliseconds}ms": score(
            combined_reference, combined_prediction, milliseconds / 1_000
        )
        for milliseconds in (20, 50, 100)
    }
    result = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmarkId": manifest["benchmarkId"],
        "selectionManifestSha256": sha256(manifest_path),
        "system": "production-equivalent Demucs htdemucs_ft + DrumToScore recall-fusion v6",
        "trackCount": len(track_results),
        "audioSeconds": sum(float(item["seconds"]) for item in items),
        "aggregate": aggregate,
        "isolatedDrumControlAggregate": {
            f"{milliseconds}ms": score(
                combined_reference,
                combined_isolated_control,
                milliseconds / 1_000,
            )
            for milliseconds in (20, 50, 100)
        },
        "tracks": track_results,
        "claimBoundary": (
            "Engineering evidence for these two constructed rights-cleared mixtures only; "
            "not a general accuracy percentage or an untouched-commercial-song claim."
        ),
    }
    result_path = output / "benchmark-result.json"
    write_json(result_path, result)
    print(
        json.dumps(
            {"result": str(result_path), "f1At50ms": aggregate["50ms"]["micro"]["f1"]},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
