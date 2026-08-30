"""Rank transcription candidates against one immutable reference set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .benchmark import evaluate_benchmark


def evaluate_candidates(
    reference_payload: dict[str, Any], candidates: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    reference_songs = reference_payload.get("songs")
    if not isinstance(reference_songs, list) or not reference_songs:
        raise ValueError("reference payload must contain songs")
    reference_ids = {str(song["id"]) for song in reference_songs}
    if len(reference_ids) != len(reference_songs):
        raise ValueError("reference song ids must be unique")
    reports: dict[str, dict[str, Any]] = {}
    for candidate_name, candidate in candidates.items():
        if not candidate_name.strip():
            raise ValueError("candidate names must not be empty")
        candidate_songs = candidate.get("songs")
        if not isinstance(candidate_songs, list):
            raise ValueError(f"candidate {candidate_name!r} must contain songs")
        predictions = {str(song["id"]): song for song in candidate_songs}
        if set(predictions) != reference_ids or len(predictions) != len(candidate_songs):
            raise ValueError(
                f"candidate {candidate_name!r} song ids must exactly match the reference set"
            )
        merged_songs = []
        for reference in reference_songs:
            song_id = str(reference["id"])
            prediction = predictions[song_id]
            merged = dict(reference)
            merged["predictions"] = prediction.get("predictions", prediction.get("hits", []))
            merged["processingSeconds"] = prediction.get("processingSeconds", 0)
            merged["providerCost"] = prediction.get("providerCost", 0)
            provider_chain = dict(reference.get("providers", {}))
            provider_chain.update(prediction.get("providers", {}))
            provider_chain["transcription"] = candidate_name
            merged["providers"] = provider_chain
            merged_songs.append(merged)
        payload = {
            **reference_payload,
            "songs": merged_songs,
            "evidenceLevel": reference_payload.get("evidenceLevel", "licensed_evaluation"),
        }
        reports[candidate_name] = evaluate_benchmark(payload)
    ranking = sorted(
        (
            {
                "candidate": name,
                "f1At25ms": report["onsetToleranceReports"]["25"]["overall"]["f1"],
                "f1At50ms": report["overall"]["f1"],
                "macroF1At50ms": report["overall"]["macroF1"],
                "precisionAt50ms": report["overall"]["precision"],
                "recallAt50ms": report["overall"]["recall"],
                "timingMaeSeconds": report["overall"]["timingMaeSeconds"],
            }
            for name, report in reports.items()
        ),
        key=lambda item: (
            -float(item["f1At50ms"]),
            -float(item["macroF1At50ms"]),
            -float(item["f1At25ms"]),
            str(item["candidate"]),
        ),
    )
    return {
        "schemaVersion": 1,
        "referenceSongCount": len(reference_songs),
        "ranking": ranking,
        "reports": reports,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument(
        "--candidate",
        action="append",
        required=True,
        help="Candidate in NAME=predictions.json form; repeat for every model.",
    )
    parser.add_argument("--json", type=Path, required=True, dest="output")
    args = parser.parse_args(argv)
    candidates: dict[str, dict[str, Any]] = {}
    for value in args.candidate:
        name, separator, filename = value.partition("=")
        if not separator or not name or not filename or name in candidates:
            parser.error("each --candidate must be a unique NAME=predictions.json value")
        candidates[name] = json.loads(Path(filename).read_text(encoding="utf-8"))
    result = evaluate_candidates(json.loads(args.reference.read_text(encoding="utf-8")), candidates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "winner": result["ranking"][0]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
