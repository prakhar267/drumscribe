from __future__ import annotations

import argparse
import json
from pathlib import Path

from .manifest import load_manifest, split_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DrumScribe ML dataset tooling")
    command = parser.add_subparsers(dest="command", required=True)
    manifest_parser = command.add_parser("manifest")
    manifest_command = manifest_parser.add_subparsers(dest="manifest_command", required=True)
    validate = manifest_command.add_parser("validate")
    validate.add_argument("input", type=Path)
    validate.add_argument("--allow-noncommercial", action="store_true")
    split = manifest_command.add_parser("split")
    split.add_argument("input", type=Path)
    split.add_argument("output", type=Path)
    split.add_argument("--seed", required=True)
    split.add_argument("--train", type=float, default=0.8)
    split.add_argument("--validation", type=float, default=0.1)
    split.add_argument("--test", type=float, default=0.1)
    args = parser.parse_args(argv)
    manifest = load_manifest(args.input)
    if args.manifest_command == "validate":
        if not args.allow_noncommercial:
            manifest.require_training_safe()
        print(
            json.dumps(
                {
                    "valid": True,
                    "tracks": len(manifest.tracks),
                    "source": manifest.source.name,
                }
            )
        )
        return 0
    payload = split_payload(
        manifest,
        seed=args.seed,
        train=args.train,
        validation=args.validation,
        test=args.test,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "tracks": len(manifest.tracks)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
