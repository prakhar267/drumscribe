from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .calibration import calibrate_confidence
from .checkpoint_eval import evaluate_checkpoint
from .egmd import import_egmd_dataset
from .ensemble import evaluate_ensemble, evaluate_stacked_ensemble
from .groove import import_groove_dataset
from .lifecycle import PreparationConfig, prepare_dataset
from .manifest import load_manifest, split_payload
from .one_shot_overlay import (
    OneShotOverlayConfig,
    create_one_shot_overlays,
    create_one_shot_probe,
)
from .one_shots import audit_one_shot_catalog
from .pilot import create_pilot_dataset
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
    egmd = command.add_parser("import-egmd")
    egmd.add_argument("dataset_root", type=Path)
    egmd.add_argument("manifest", type=Path)
    egmd.add_argument("--metadata", type=Path)
    egmd.add_argument("--archive", type=Path)
    egmd.add_argument("--overwrite", action="store_true")
    one_shots = command.add_parser("audit-one-shots")
    one_shots.add_argument("catalog", type=Path)
    one_shots.add_argument("library_root", type=Path)
    one_shots.add_argument("output", type=Path)
    pilot = command.add_parser("create-pilot")
    pilot.add_argument("source", type=Path)
    pilot.add_argument("output", type=Path)
    pilot.add_argument("--seed", required=True)
    pilot.add_argument("--train-groups", type=int, default=100)
    pilot.add_argument("--validation-groups", type=int, default=20)
    overlay = command.add_parser("overlay-one-shots")
    overlay.add_argument("prepared_dataset", type=Path)
    overlay.add_argument("catalog", type=Path)
    overlay.add_argument("library_root", type=Path)
    overlay.add_argument("output_root", type=Path)
    overlay.add_argument("--seed", required=True)
    overlay.add_argument("--classes", nargs="+", default=["LOW_TOM", "TAMBOURINE"])
    overlay.add_argument("--variants-per-record", type=int, default=1)
    overlay.add_argument("--hits-per-class", type=int, default=1)
    overlay.add_argument("--record-limit", type=int)
    probe = command.add_parser("create-one-shot-probe")
    probe.add_argument("prepared_dataset", type=Path)
    probe.add_argument("catalog", type=Path)
    probe.add_argument("library_root", type=Path)
    probe.add_argument("output_root", type=Path)
    probe.add_argument("--seed", required=True)
    probe.add_argument("--classes", nargs="+", default=["LOW_TOM", "TAMBOURINE"])
    probe.add_argument("--hits-per-class", type=int, default=1)
    probe.add_argument("--record-limit", type=int)
    evaluate = command.add_parser("evaluate-checkpoint")
    evaluate.add_argument("checkpoint", type=Path)
    evaluate.add_argument("prepared_dataset", type=Path)
    evaluate.add_argument("output", type=Path)
    evaluate.add_argument("--device", default="auto")
    evaluate.add_argument("--split", choices=("train", "validation", "test"))
    evaluate.add_argument("--fixed-checkpoint-thresholds", action="store_true")
    evaluate.add_argument("--family-competition", action="store_true")
    evaluate_ensemble_parser = command.add_parser("evaluate-ensemble")
    evaluate_ensemble_parser.add_argument("config", type=Path)
    evaluate_ensemble_parser.add_argument("primary_checkpoint", type=Path)
    evaluate_ensemble_parser.add_argument("secondary_checkpoint", type=Path)
    evaluate_ensemble_parser.add_argument("prepared_dataset", type=Path)
    evaluate_ensemble_parser.add_argument("output", type=Path)
    evaluate_ensemble_parser.add_argument("--device", default="auto")
    evaluate_ensemble_parser.add_argument("--split", choices=("train", "validation", "test"))
    evaluate_stack_parser = command.add_parser("evaluate-stacked-ensemble")
    evaluate_stack_parser.add_argument("config", type=Path)
    evaluate_stack_parser.add_argument("prepared_dataset", type=Path)
    evaluate_stack_parser.add_argument("output", type=Path)
    evaluate_stack_parser.add_argument(
        "--checkpoint",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help="named checkpoint from the stack config; repeat for every model",
    )
    evaluate_stack_parser.add_argument("--device", default="auto")
    evaluate_stack_parser.add_argument("--split", choices=("train", "validation", "test"))
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
    if args.command == "import-egmd":
        imported = import_egmd_dataset(
            args.dataset_root,
            args.manifest,
            metadata_path=args.metadata,
            archive_path=args.archive,
            overwrite=args.overwrite,
        )
        print(
            json.dumps(
                {
                    "manifest": str(args.manifest),
                    "tracks": len(imported.tracks),
                    "performanceGroups": len({track.group_id for track in imported.tracks}),
                }
            )
        )
        return 0
    if args.command == "audit-one-shots":
        audit = audit_one_shot_catalog(args.catalog, args.library_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(audit, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "trainingReady": audit["trainingReady"],
                    "corpusSha256": audit["corpusSha256"],
                }
            )
        )
        return 0 if audit["trainingReady"] else 2
    if args.command == "create-pilot":
        output = create_pilot_dataset(
            args.source,
            args.output,
            seed=args.seed,
            train_groups=args.train_groups,
            validation_groups=args.validation_groups,
        )
        payload = json.loads(output.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "output": str(output),
                    "trainGroups": len(payload["pilotSelection"]["selectedGroups"]["train"]),
                    "validationGroups": len(
                        payload["pilotSelection"]["selectedGroups"]["validation"]
                    ),
                    "testRecords": 0,
                }
            )
        )
        return 0
    if args.command == "overlay-one-shots":
        output = create_one_shot_overlays(
            args.prepared_dataset,
            args.catalog,
            args.library_root,
            args.output_root,
            config=OneShotOverlayConfig(
                seed=args.seed,
                classes=tuple(args.classes),
                variants_per_record=args.variants_per_record,
                hits_per_class=args.hits_per_class,
                record_limit=args.record_limit,
            ),
        )
        payload = json.loads(output.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "output": str(output),
                    "generatedRecords": payload["oneShotOverlay"]["generatedRecords"],
                    "generatedEventCounts": payload["oneShotOverlay"]["generatedEventCounts"],
                    "untouchedSplits": payload["oneShotOverlay"]["untouchedSplits"],
                }
            )
        )
        return 0
    if args.command == "create-one-shot-probe":
        output = create_one_shot_probe(
            args.prepared_dataset,
            args.catalog,
            args.library_root,
            args.output_root,
            config=OneShotOverlayConfig(
                seed=args.seed,
                classes=tuple(args.classes),
                hits_per_class=args.hits_per_class,
                record_limit=args.record_limit,
            ),
        )
        payload = json.loads(output.read_text(encoding="utf-8"))
        print(json.dumps({"output": str(output), **payload["oneShotProbe"]}))
        return 0
    if args.command == "evaluate-checkpoint":
        output = evaluate_checkpoint(
            args.checkpoint,
            args.prepared_dataset,
            args.output,
            device=args.device,
            split=args.split,
            fixed_checkpoint_thresholds=args.fixed_checkpoint_thresholds,
            family_competition=args.family_competition,
        )
        print(output.read_text(encoding="utf-8"), end="")
        return 0
    if args.command == "evaluate-ensemble":
        output = evaluate_ensemble(
            args.config,
            args.primary_checkpoint,
            args.secondary_checkpoint,
            args.prepared_dataset,
            args.output,
            device=args.device,
            split=args.split,
        )
        print(output.read_text(encoding="utf-8"), end="")
        return 0
    if args.command == "evaluate-stacked-ensemble":
        output = evaluate_stacked_ensemble(
            args.config,
            _named_checkpoints(args.checkpoint),
            args.prepared_dataset,
            args.output,
            device=args.device,
            split=args.split,
        )
        print(output.read_text(encoding="utf-8"), end="")
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


def _named_checkpoints(values: list[str]) -> dict[str, Path]:
    checkpoints: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name.strip() or not raw_path.strip():
            raise ValueError("stacked checkpoint arguments must use NAME=PATH")
        if name in checkpoints:
            raise ValueError(f"duplicate stacked checkpoint name: {name}")
        checkpoints[name] = Path(raw_path)
    return checkpoints


if __name__ == "__main__":
    raise SystemExit(main())
