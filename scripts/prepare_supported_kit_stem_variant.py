#!/usr/bin/env python3
"""Prepare a separated-stem variant of a frozen supported-kit test record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    source = json.loads(args.prepared_dataset.resolve(strict=True).read_text())
    records = source.get("records", [])
    if len(records) != 1 or records[0].get("split") != "test":
        raise ValueError("source must contain exactly one frozen test record")
    stem = args.stem.resolve(strict=True)
    feature_path = args.output.parent / "separated-drum-features.npz"
    if feature_path.exists():
        raise FileExistsError(feature_path)
    cache_log_mel(
        stem,
        feature_path,
        PreparationConfig(seed="supported-kit-separated-test", augmentation_variants=0),
    )
    record = dict(records[0])
    record.update(
        {
            "audioPath": str(stem),
            "audioSha256": _sha256(stem),
            "featurePath": str(feature_path.resolve()),
            "variant": "htdemucs-ft-separated-full-mix",
        }
    )
    payload = dict(source)
    payload["dataset"] = {
        "name": "MuldjordKit synthetic metal full-mix, Demucs-separated",
        "version": "1",
        "sourceType": "synthetic",
    }
    payload["records"] = [record]
    payload["separation"] = {
        "provider": "htdemucs_ft",
        "sourcePreparedDatasetSha256": _sha256(
            args.prepared_dataset.resolve(strict=True)
        ),
    }
    payload["datasetManifestHash"] = hashlib.sha256(
        json.dumps([record], sort_keys=True).encode()
    ).hexdigest()
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
