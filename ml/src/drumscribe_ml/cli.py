from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .calibration import calibrate_confidence
from .groove import import_groove_dataset
from .lifecycle import PreparationConfig, prepare_dataset
from .manifest import load_manifest, split_payload
from .quality import evaluate_accuracy_gate
from .training import TrainingConfig, run_training


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
    prepare = command.add_parser("prepare")
    prepare.add_argument("manifest", type=Path)
    prepare.add_argument("dataset_root", type=Path)
    prepare.add_argument("output_root", type=Path)
    prepare.add_argument("--seed", required=True)
    prepare.add_argument("--augmentation-variants", type=int, default=2)
    train = command.add_parser("train")
    train.add_argument("config", type=Path)
    calibrate = command.add_parser("calibrate")
    calibrate.add_argument("input", type=Path, help="NPZ containing logits and targets")
    calibrate.add_argument("output", type=Path)
    quality_gate = command.add_parser("quality-gate")
    quality_gate.add_argument("benchmark", type=Path)
    quality_gate.add_argument("evidence", type=Path)
    groove = command.add_parser("import-groove")
    groove.add_argument("dataset_root", type=Path)
    groove.add_argument("manifest", type=Path)
    groove.add_argument("--archive", type=Path)
    groove.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        destination = prepare_dataset(
            load_manifest(args.manifest),
            dataset_root=args.dataset_root,
            output_root=args.output_root,
            config=PreparationConfig(
                seed=args.seed,
                augmentation_variants=args.augmentation_variants,
            ),
        )
        print(json.dumps({"preparedDataset": str(destination)}))
        return 0
    if args.command == "train":
        print(json.dumps({"experiment": str(run_training(TrainingConfig.load(args.config)))}))
        return 0
    if args.command == "calibrate":
        arrays = np.load(args.input)
        result = calibrate_confidence(arrays["logits"], arrays["targets"])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(asdict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({"calibration": str(args.output)}))
        return 0
    if args.command == "quality-gate":
        result = evaluate_accuracy_gate(
            json.loads(args.benchmark.read_text(encoding="utf-8")),
            json.loads(args.evidence.read_text(encoding="utf-8")),
        )
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return 0 if result.passed else 2
    if args.command == "import-groove":
        imported = import_groove_dataset(
            args.dataset_root,
            args.manifest,
            archive_path=args.archive,
            overwrite=args.overwrite,
        )
        print(json.dumps({"manifest": str(args.manifest), "tracks": len(imported.tracks)}))
        return 0

    manifest = load_manifest(args.input)
    if args.manifest_command == "validate":
        if not args.allow_noncommercial:
            manifest.require_training_safe()
        print(
            json.dumps(
                {"valid": True, "tracks": len(manifest.tracks), "source": manifest.source.name}
            )
        )
        return 0
    payload = split_payload(
        manifest, seed=args.seed, train=args.train, validation=args.validation, test=args.test
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "tracks": len(manifest.tracks)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
