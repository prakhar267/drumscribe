#!/usr/bin/env python3
"""Add an already-opened separated development stem to a training corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import soundfile as sf
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-dataset", type=Path, required=True)
    parser.add_argument("--stem", type=Path, required=True)
    parser.add_argument("--annotation", type=Path, required=True)
    parser.add_argument("--track-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    source_path = args.prepared_dataset.resolve(strict=True)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if source.get("evaluationOnly"):
        raise ValueError("cannot add a development record to evaluation-only data")
    stem = args.stem.resolve(strict=True)
    annotation = args.annotation.resolve(strict=True)
    annotation_payload = json.loads(annotation.read_text(encoding="utf-8"))
    if not annotation_payload.get("events"):
        raise ValueError("development annotation contains no events")
    feature_path = args.output.parent / "domain-features" / f"{args.track_id}.npz"
    if feature_path.exists():
        raise FileExistsError(feature_path)
    cache_log_mel(
        stem,
        feature_path,
        PreparationConfig(seed=args.track_id, augmentation_variants=0),
    )
    info = sf.info(stem)
    record = {
        "trackId": args.track_id,
        "groupId": args.track_id,
        "split": "train",
        "variant": "opened-development-htdemucs-ft",
        "audioPath": str(stem),
        "audioSha256": _sha256(stem),
        "annotationPath": str(annotation),
        "featurePath": str(feature_path.resolve()),
        "augmentation": None,
        "durationSeconds": info.frames / info.samplerate,
    }
    records = [*source.get("records", []), record]
    payload = dict(source)
    payload["dataset"] = {
        "name": "MuldjordKit synthetic full-kit plus opened separation development",
        "version": "2",
        "sourceType": "synthetic_hybrid",
    }
    payload["datasetManifestHash"] = hashlib.sha256(
        json.dumps(records, sort_keys=True).encode()
    ).hexdigest()
    payload["records"] = records
    payload["domainAdaptation"] = {
        "trackId": args.track_id,
        "sourcePreparedDatasetSha256": _sha256(source_path),
        "status": "opened_development_only",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
