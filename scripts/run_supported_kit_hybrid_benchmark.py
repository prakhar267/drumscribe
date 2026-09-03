#!/usr/bin/env python3
"""Generate, predict, and score the frozen DrumScribe hybrid holdout suite."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import run_hard_metal_market_benchmark as market
from drumscribe_music import RawDrumHit, complete_rhythm
from drumscribe_music.providers.research import ResearchBeatThisTrackingProvider
from model_runners.drumscribe_hybrid_runner import transcribe
from run_competitive_drum_benchmark import FAMILY_SIX_MAP, score_taxonomies

HOLDOUT_TRACKS = (
    market.TrackSpec("01-blackened-engine", "Blackened Engine", "thrash", 206.0, 7101),
    market.TrackSpec("02-faultline", "Faultline", "nu-metal", 96.0, 7202),
    market.TrackSpec("03-glass-hammer", "Glass Hammer", "metalcore", 164.0, 7303),
    market.TrackSpec("04-redline-blast", "Redline Blast", "death-metal", 212.0, 7404),
    market.TrackSpec("05-sunken-mass", "Sunken Mass", "doom-metal", 78.0, 7505),
    market.TrackSpec("06-forged-groove", "Forged Groove", "groove-metal", 116.0, 7606),
    market.TrackSpec(
        "07-static-foundry", "Static Foundry", "industrial-metal", 134.0, 7707
    ),
    market.TrackSpec(
        "08-shifting-axis", "Shifting Axis", "progressive-metal", 146.0, 7808
    ),
    market.TrackSpec("09-ember-gallop", "Ember Gallop", "power-metal", 176.0, 7909),
    market.TrackSpec("10-cinder-dbeat", "Cinder D-Beat", "hardcore", 200.0, 8010),
)
CONTINUOUS_FAMILIES = frozenset({"CYMBAL", "HIHAT"})


def _generate(args: argparse.Namespace) -> None:
    market.TRACKS = HOLDOUT_TRACKS
    args.suite_name = "supported-kit-hybrid-holdout-v1"
    market.generate_suite(args)


def _predict(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    repository = args.repository.resolve(strict=True)
    destination = output / "hybrid-v1"
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir()
    tracks: list[dict[str, Any]] = []
    for spec in HOLDOUT_TRACKS:
        stem = (
            args.demucs_root.resolve(strict=True)
            / "htdemucs_ft"
            / spec.slug
            / "drums.wav"
        )
        payload = transcribe(
            source=stem.resolve(strict=True),
            repository=repository,
            ensemble_config=(repository / args.ensemble_config).resolve(strict=True),
            oaf_checkpoint=(repository / args.oaf_checkpoint).resolve(strict=True),
            oaf_decoder=(repository / args.oaf_decoder).resolve(strict=True),
            device=args.device,
        )
        prediction_path = destination / f"{spec.slug}.json"
        market._write_json_new(prediction_path, payload)
        tracks.append(
            {
                "track": spec.slug,
                "events": len(payload["hits"]),
                "predictionSha256": market._sha256(prediction_path),
            }
        )
        print(json.dumps(tracks[-1]), flush=True)
    market._write_json_new(
        destination / "prediction-manifest.json",
        {
            "schemaVersion": 1,
            "createdAt": datetime.now(UTC).isoformat(),
            "referenceFilesRead": False,
            "policyFrozenBeforeHoldoutGeneration": True,
            "tracks": tracks,
        },
    )


def _score(args: argparse.Namespace) -> None:
    output = args.output.resolve(strict=True)
    prediction_root = output / args.prediction_name
    destination = output / args.result_name
    if destination.exists():
        raise FileExistsError(destination)
    per_track = []
    for spec in HOLDOUT_TRACKS:
        reference_payload = json.loads(
            (output / "tracks" / spec.slug / "reference-events.json").read_text(
                encoding="utf-8"
            )
        )
        prediction_payload = json.loads(
            (prediction_root / f"{spec.slug}.json").read_text(encoding="utf-8")
        )
        reference = sorted(
            (float(event["onsetSeconds"]), str(event["instrument"]))
            for event in reference_payload["events"]
            if 0 <= float(event["onsetSeconds"]) < market.WINDOW_SECONDS
        )
        prediction = sorted(
            (float(hit["onsetSeconds"]), str(hit["instrument"]))
            for hit in prediction_payload["hits"]
            if 0 <= float(hit["onsetSeconds"]) < market.WINDOW_SECONDS
        )
        scores = {
            f"{milliseconds}ms": score_taxonomies(
                reference,
                prediction,
                milliseconds / 1000,
            )
            for milliseconds in (20, 50)
        }
        per_track.append(
            {
                **asdict(spec),
                "referenceEvents": len(reference),
                "predictedEvents": len(prediction),
                "scores": scores,
                "hashes": {
                    "reference": market._sha256(
                        output / "tracks" / spec.slug / "reference-events.json"
                    ),
                    "prediction": market._sha256(prediction_root / f"{spec.slug}.json"),
                },
            }
        )
        print(json.dumps({"scored": spec.slug}), flush=True)
    aggregate = {
        f"{milliseconds}ms": market._aggregate_taxonomies(
            [track["scores"][f"{milliseconds}ms"] for track in per_track]
        )
        for milliseconds in (20, 50)
    }
    comparison_path = args.comparison.resolve(strict=True)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    competitor_target = comparison["aggregate"]["20ms"]["drum2notes"]["family6"][
        "micro"
    ]["f1"]
    hybrid_f1 = aggregate["20ms"]["family6"]["micro"]["f1"]
    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "Ten untouched rights-cleared supported-kit hard-metal holdouts",
            "status": (
                "opened_development_probe"
                if args.opened_development
                else "sealed_post_freeze_holdout"
            ),
            "trackCount": len(HOLDOUT_TRACKS),
            "referenceFrozenBeforePrediction": True,
            "predictionManifestReferenceFilesRead": (
                None if args.opened_development else False
            ),
            "postTestTuning": args.opened_development,
            "rightsCleared": True,
            "limitations": [
                "This measures deterministic synthetic arrangements rendered with one CC BY 4.0 acoustic kit, not commercial masters.",
                "The comparison target comes from the earlier shared ten-track suite; Drum2Notes was not rerun on this holdout.",
                "Demucs checkpoint licensing remains unresolved for a commercial production launch.",
            ],
        },
        "aggregate": aggregate,
        "comparisonTarget": {
            "system": "Drum2Notes",
            "metric": "family6 micro F1 at 20ms",
            "f1": competitor_target,
            "sourceSha256": market._sha256(comparison_path),
            "met": hybrid_f1 >= competitor_target,
            "marginPercentagePoints": (hybrid_f1 - competitor_target) * 100,
        },
        "tracks": per_track,
    }
    market._write_json_new(destination, report)
    print(
        json.dumps(
            {
                "result": str(destination),
                "hybridFamily6MicroF1At20ms": hybrid_f1,
                "competitorTarget": competitor_target,
                "met": hybrid_f1 >= competitor_target,
            }
        )
    )


def _research_fusion(args: argparse.Namespace) -> None:
    """Reproduce the post-unsealing ADTOF/first-party research diagnostic.

    The command does not read annotations, but the suite was already opened
    before this policy was developed. Its outputs must therefore be scored with
    ``--opened-development`` and never described as a fresh holdout.
    """

    output = args.output.resolve(strict=True)
    hybrid_root = output / args.hybrid_prediction_name
    adtof_root = output / args.adtof_prediction_name
    destination = output / args.prediction_name
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir()
    beat_tracker = ResearchBeatThisTrackingProvider(
        device=None if args.device == "auto" else args.device
    )
    rows = []
    for spec in HOLDOUT_TRACKS:
        hybrid_path = hybrid_root / f"{spec.slug}.json"
        adtof_path = adtof_root / f"{spec.slug}.json"
        hybrid = json.loads(hybrid_path.read_text(encoding="utf-8"))
        adtof = json.loads(adtof_path.read_text(encoding="utf-8"))
        selected = [
            hit
            for hit in hybrid["hits"]
            if FAMILY_SIX_MAP.get(str(hit["instrument"])) not in CONTINUOUS_FAMILIES
        ]
        selected.extend(
            hit
            for hit in adtof["hits"]
            if FAMILY_SIX_MAP.get(str(hit["instrument"])) in CONTINUOUS_FAMILIES
        )
        completion = complete_rhythm(
            (
                RawDrumHit(
                    hit["instrument"],
                    float(hit["onsetSeconds"]),
                    int(hit.get("velocity", 100)),
                    float(hit.get("confidence", 0.5)),
                    metadata={"sourceModel": hit.get("sourceModel")},
                )
                for hit in selected
            ),
            beat_tracker.track(output / "tracks" / spec.slug / "full-mix.wav"),
        )
        payload = {
            "schemaVersion": 1,
            "provider": "drumscribe-best-research-v3",
            "modelVersion": "drumscribe-hybrid-v1+adtof-continuous+rhythm-completion-v3",
            "researchOnly": True,
            "openedDevelopmentProbe": True,
            "rhythmCompletion": {
                "applied": completion.applied,
                **dict(completion.metadata),
            },
            "hits": [
                {
                    "instrument": str(hit.instrument_class),
                    "onsetSeconds": round(hit.onset_seconds, 6),
                    "velocity": hit.velocity,
                    "confidence": round(hit.confidence, 6),
                }
                for hit in completion.hits
            ],
        }
        prediction_path = destination / f"{spec.slug}.json"
        market._write_json_new(prediction_path, payload)
        rows.append(
            {
                "track": spec.slug,
                "events": len(payload["hits"]),
                "sources": {
                    "hybrid": market._sha256(hybrid_path),
                    "adtof": market._sha256(adtof_path),
                },
                "predictionSha256": market._sha256(prediction_path),
            }
        )
        print(json.dumps(rows[-1]), flush=True)
    market._write_json_new(
        destination / "prediction-manifest.json",
        {
            "schemaVersion": 1,
            "createdAt": datetime.now(UTC).isoformat(),
            "referenceFilesRead": False,
            "openedDevelopmentProbe": True,
            "tracks": rows,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    generate = subcommands.add_parser("generate")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--kit", type=Path, default=market.KIT_PATH)
    predict = subcommands.add_parser("predict")
    predict.add_argument("--output", type=Path, required=True)
    predict.add_argument("--demucs-root", type=Path, required=True)
    predict.add_argument("--repository", type=Path, default=Path.cwd())
    predict.add_argument(
        "--ensemble-config",
        type=Path,
        default=Path("ml/configs/groove-stacked-articulation-v16.json"),
    )
    predict.add_argument(
        "--oaf-checkpoint",
        type=Path,
        default=Path("ml/models/supported-kit-oaf-v24.pt"),
    )
    predict.add_argument(
        "--oaf-decoder",
        type=Path,
        default=Path("ml/models/supported-kit-oaf-v24-demucs-subframe-decoder.json"),
    )
    predict.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    fusion = subcommands.add_parser("research-fusion")
    fusion.add_argument("--output", type=Path, required=True)
    fusion.add_argument("--hybrid-prediction-name", default="hybrid-v1")
    fusion.add_argument("--adtof-prediction-name", default="adtof-v1-raw")
    fusion.add_argument("--prediction-name", default="best-research-v3")
    fusion.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    score = subcommands.add_parser("score")
    score.add_argument("--output", type=Path, required=True)
    score.add_argument(
        "--comparison",
        type=Path,
        default=Path(
            "output/hard-metal-market-benchmark-2026-09-02/benchmark-result.json"
        ),
    )
    score.add_argument("--prediction-name", default="hybrid-v1")
    score.add_argument("--result-name", default="benchmark-result.json")
    score.add_argument(
        "--opened-development",
        action="store_true",
        help="mark a post-unsealing diagnostic so it cannot be reported as a holdout",
    )
    args = parser.parse_args()
    if args.command == "generate":
        _generate(args)
    elif args.command == "predict":
        _predict(args)
    elif args.command == "research-fusion":
        _research_fusion(args)
    else:
        _score(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
