#!/usr/bin/env python3
"""Run the clean-room DrumScribe kit-adaptive checkpoint contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from drumscribe_ml.kit_adapter import KitAdapterModel, transcribe_wav

PROVIDER = "drumscribe-kit-adaptive-v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = KitAdapterModel.load(args.model)
    predictions = transcribe_wav(args.input, model)
    payload = {
        "schemaVersion": 1,
        "provider": PROVIDER,
        "modelVersion": model.model_version,
        "hits": [
            {
                "instrument": item.instrument.value,
                "onsetSeconds": round(item.onset_seconds, 6),
                "velocity": item.velocity,
                "confidence": round(item.confidence, 7),
            }
            for item in predictions
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
