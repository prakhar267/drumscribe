#!/usr/bin/env python3
"""Train and cross-validate the research-only RWC temporal stacker."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_ml.temporal_stacker import (
    DEFAULT_SOURCE_ORDER,
    EventFusionRule,
    build_temporal_stacker,
    fuse_event_streams,
    temporal_context_features,
)
from drumscribe_ml.training import TRAINING_CLASSES, _match_frames, _peak_frames

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from run_competitive_drum_benchmark import match_times, sha256
from run_rwc_popular_50_benchmark import (
    aggregate_scores,
    load_and_validate_manifest,
    reference_events_from_track,
    write_json,
)

DEFAULT_DATA_ROOT = Path("data/research-corpus/rwc-popular-50-v1")
DEFAULT_PROBABILITY_ROOT = Path("output/rwc-popular-50-development")
DEFAULT_BASE_ROOT = Path("output/rwc-popular-50-v19-development/drumscribe-raw")
DEFAULT_CHECKPOINT = Path("ml/models/rwc-temporal-stacker-v20.pt")
DEFAULT_CONFIG = Path("ml/configs/rwc-temporal-stacker-v20.json")
DEFAULT_EVIDENCE = Path("output/rwc-temporal-stacker-v20-training.json")
PROBABILITY_DIRECTORIES = {
    "stemEnsemble": "v18-probabilities",
    "stemSpecialist": "focal-v18-probabilities",
    "mixtureEnsemble": "v18-fullmix-probabilities",
    "mixtureSpecialist": "focal-v18-fullmix-probabilities",
}
OFFSETS = (-6, -4, -2, 0, 2, 4, 6)
THRESHOLDS = tuple(
    float(value)
    for value in np.concatenate(
        (np.linspace(0.05, 0.95, 37), np.linspace(0.96, 0.999, 40))
    )
)
DISTANCES = (3, 4, 5, 6, 8, 10, 12)
SHIFTS = tuple(range(-4, 3))
FUSION_RADII = (2, 3, 4, 5, 6, 8, 10)
CLASS_NAMES = tuple(instrument.value for instrument in TRAINING_CLASSES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument(
        "--probability-root", type=Path, default=DEFAULT_PROBABILITY_ROOT
    )
    parser.add_argument("--base-root", type=Path, default=DEFAULT_BASE_ROOT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260904)
    parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    return parser.parse_args()


def resolve(repository: Path, path: Path, *, strict: bool = True) -> Path:
    candidate = path if path.is_absolute() else repository / path
    return candidate.resolve(strict=strict)


def choose_device(requested: str) -> str:
    import torch

    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def target_matrix(
    track: dict[str, Any], frame_count: int, frame_seconds: float
) -> tuple[np.ndarray, list[list[int]]]:
    class_index = {name: index for index, name in enumerate(CLASS_NAMES)}
    targets = np.zeros((frame_count, len(CLASS_NAMES)), dtype=np.float32)
    references: list[list[int]] = [[] for _ in CLASS_NAMES]
    for event in track["referenceEvents"]:
        frame = min(
            frame_count - 1, round(float(event["onsetSeconds"]) / frame_seconds)
        )
        index = class_index[event["instrument"]]
        targets[max(0, frame - 2) : min(frame_count, frame + 3), index] = 1
        references[index].append(frame)
    return targets, references


def load_inputs(
    probability_root: Path,
    base_root: Path,
    tracks: list[dict[str, Any]],
) -> tuple[
    list[np.ndarray],
    list[np.ndarray],
    list[list[list[int]]],
    list[list[tuple[int, str]]],
    float,
]:
    features: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    references: list[list[list[int]]] = []
    base_events: list[list[tuple[int, str]]] = []
    frame_seconds: float | None = None
    for track in tracks:
        rwc_id = track["rwcId"]
        sources: dict[str, np.ndarray] = {}
        for source in DEFAULT_SOURCE_ORDER:
            path = probability_root / PROBABILITY_DIRECTORIES[source] / f"{rwc_id}.npz"
            with np.load(path, allow_pickle=False) as arrays:
                sources[source] = arrays["probabilities"].astype(np.float32)
                if (
                    int(arrays["sample_rate"]) != 22_050
                    or int(arrays["hop_length"]) != 220
                ):
                    raise RuntimeError(f"unexpected probability frame rate: {path}")
                source_frame_seconds = int(arrays["hop_length"]) / int(
                    arrays["sample_rate"]
                )
                if frame_seconds is None:
                    frame_seconds = source_frame_seconds
                elif not np.isclose(frame_seconds, source_frame_seconds):
                    raise RuntimeError(f"inconsistent probability frame rate: {path}")
        context = temporal_context_features(sources, offsets=OFFSETS)
        assert frame_seconds is not None
        target, reference = target_matrix(track, len(context), frame_seconds)
        raw = json.loads((base_root / f"{rwc_id}.json").read_text(encoding="utf-8"))
        features.append(context)
        targets.append(target)
        references.append(reference)
        base_events.append(
            [
                (
                    round(float(hit["onsetSeconds"]) / frame_seconds),
                    str(hit["instrument"]),
                )
                for hit in raw["hits"]
            ]
        )
    assert frame_seconds is not None
    return features, targets, references, base_events, frame_seconds


def train_model(
    features: list[np.ndarray],
    targets: list[np.ndarray],
    indices: list[int],
    *,
    epochs: int,
    seed: int,
    device: str,
):
    import torch

    torch.manual_seed(seed)
    np.random.seed(seed)
    training_features = np.concatenate([features[index] for index in indices])
    training_targets = np.concatenate([targets[index] for index in indices])
    mean = training_features.mean(axis=0).astype(np.float32)
    standard_deviation = (training_features.std(axis=0) + 0.1).astype(np.float32)
    normalized = (training_features - mean) / standard_deviation
    positive = training_targets.sum(axis=0)
    weights = np.clip(
        ((len(training_targets) - positive) / np.maximum(positive, 1)) ** 0.6,
        1,
        60,
    ).astype(np.float32)
    model = build_temporal_stacker(training_features.shape[1]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.0004, weight_decay=0.0001)
    feature_tensor = torch.from_numpy(normalized)
    target_tensor = torch.from_numpy(training_targets)
    positive_weights = torch.from_numpy(weights).to(device)
    generator = torch.Generator().manual_seed(seed)
    losses: list[float] = []
    for _epoch in range(epochs):
        model.train()
        permutation = torch.randperm(len(feature_tensor), generator=generator)
        for start in range(0, len(permutation), 1_024):
            batch = permutation[start : start + 1_024]
            expected = target_tensor[batch].to(device)
            logits = model(feature_tensor[batch].to(device))
            base_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                logits,
                expected,
                pos_weight=positive_weights,
                reduction="none",
            )
            probability = torch.sigmoid(logits)
            target_probability = probability * expected + (1 - probability) * (
                1 - expected
            )
            loss = (base_loss * (1 - target_probability)).mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
    return model, mean, standard_deviation, float(np.mean(losses[-100:]))


def infer(
    model,
    features: list[np.ndarray],
    indices: Iterable[int],
    mean: np.ndarray,
    standard_deviation: np.ndarray,
    *,
    device: str,
) -> dict[int, np.ndarray]:
    import torch

    output: dict[int, np.ndarray] = {}
    model.eval()
    with torch.no_grad():
        for index in indices:
            normalized = (features[index] - mean) / standard_deviation
            logits = model(torch.from_numpy(normalized).to(device))
            output[index] = torch.sigmoid(logits).cpu().numpy()
    return output


def counts_for_frames(
    references: list[list[list[int]]],
    indices: Iterable[int],
    class_index: int,
    predictions: dict[int, list[int]],
) -> tuple[int, int, int]:
    true_positive = false_positive = false_negative = 0
    for index in indices:
        matched = _match_frames(
            references[index][class_index], predictions[index], tolerance=5
        )
        true_positive += matched[0]
        false_positive += matched[1]
        false_negative += matched[2]
    return true_positive, false_positive, false_negative


def f1(counts: tuple[int, int, int]) -> float:
    true_positive, false_positive, false_negative = counts
    denominator = 2 * true_positive + false_positive + false_negative
    return 2 * true_positive / denominator if denominator else 0.0


def tune_decoder(
    probabilities: dict[int, np.ndarray],
    references: list[list[list[int]]],
    indices: list[int],
) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    for class_index, name in enumerate(CLASS_NAMES):
        best = (0.0, 0.99, 8, 0, (0, 0, 0))
        for distance in DISTANCES:
            candidates = {
                index: [
                    (frame, float(probabilities[index][frame, class_index]))
                    for frame in _peak_frames(
                        probabilities[index][:, class_index],
                        threshold=-1,
                        minimum_distance_frames=distance,
                    )
                ]
                for index in indices
            }
            for threshold in THRESHOLDS:
                for shift in SHIFTS:
                    decoded = {
                        index: [
                            frame + shift
                            for frame, probability in candidates[index]
                            if probability >= threshold
                            and 0 <= frame + shift < len(probabilities[index])
                        ]
                        for index in indices
                    }
                    counts = counts_for_frames(
                        references, indices, class_index, decoded
                    )
                    score = f1(counts)
                    if (score, -abs(threshold - 0.5), -distance, -abs(shift)) > (
                        best[0],
                        -abs(best[1] - 0.5),
                        -best[2],
                        -abs(best[3]),
                    ):
                        best = (score, threshold, distance, shift, counts)
        rules[name] = {
            "threshold": best[1],
            "peakDistanceFrames": best[2],
            "onsetShiftFrames": best[3],
            "calibrationF1": best[0],
            "calibrationCounts": counts_payload(best[4]),
        }
    return rules


def decode(
    probabilities: dict[int, np.ndarray],
    rules: dict[str, dict[str, Any]],
    indices: Iterable[int],
) -> dict[int, list[tuple[int, str]]]:
    result: dict[int, list[tuple[int, str]]] = {}
    for index in indices:
        events: list[tuple[int, str]] = []
        for class_index, name in enumerate(CLASS_NAMES):
            rule = rules[name]
            frames = _peak_frames(
                probabilities[index][:, class_index],
                threshold=float(rule["threshold"]),
                minimum_distance_frames=int(rule["peakDistanceFrames"]),
            )
            events.extend(
                (frame + int(rule["onsetShiftFrames"]), name)
                for frame in frames
                if 0
                <= frame + int(rule["onsetShiftFrames"])
                < len(probabilities[index])
            )
        result[index] = sorted(events)
    return result


def class_lists(events: list[tuple[int, str]], name: str, shift: int = 0) -> list[int]:
    return sorted(
        frame + shift for frame, label in events if label == name and frame + shift >= 0
    )


def score_event_lists(
    references: list[list[list[int]]],
    class_index: int,
    predictions: dict[int, list[int]],
) -> tuple[int, int, int]:
    true_positive = false_positive = false_negative = 0
    for index, predicted in predictions.items():
        matched = match_times(references[index][class_index], predicted, 5)
        true_positive += int(matched["tp"])
        false_positive += int(matched["fp"])
        false_negative += int(matched["fn"])
    return true_positive, false_positive, false_negative


def merge(first: list[int], second: list[int], radius: int) -> list[int]:
    output = list(first)
    for frame in second:
        if not any(abs(frame - candidate) <= radius for candidate in output):
            output.append(frame)
    return sorted(output)


def intersect(first: list[int], second: list[int], radius: int) -> list[int]:
    return [
        frame
        for frame in first
        if any(abs(frame - candidate) <= radius for candidate in second)
    ]


def optimize_fusion(
    references: list[list[list[int]]],
    base_events: list[list[tuple[int, str]]],
    stacker_events: dict[int, list[tuple[int, str]]],
) -> tuple[dict[str, int], dict[str, dict[str, Any]], dict[str, Any]]:
    indices = list(range(len(base_events)))
    base_shifts: dict[str, int] = {}
    choices: dict[
        str, dict[str, tuple[dict[int, list[int]], tuple[int, int, int]]]
    ] = {}
    for class_index, name in enumerate(CLASS_NAMES):
        shift = max(
            SHIFTS,
            key=lambda candidate: f1(
                score_event_lists(
                    references,
                    class_index,
                    {
                        index: class_lists(base_events[index], name, candidate)
                        for index in indices
                    },
                )
            ),
        )
        base_shifts[name] = shift
        base = {
            index: class_lists(base_events[index], name, shift) for index in indices
        }
        stacker = {index: class_lists(stacker_events[index], name) for index in indices}
        candidates: dict[str, dict[int, list[int]]] = {
            "base": base,
            "stacker": stacker,
        }
        for radius in FUSION_RADII:
            candidates[f"union:{radius}"] = {
                index: merge(base[index], stacker[index], radius) for index in indices
            }
            candidates[f"intersection:{radius}"] = {
                index: intersect(base[index], stacker[index], radius)
                for index in indices
            }
        choices[name] = {
            key: (value, score_event_lists(references, class_index, value))
            for key, value in candidates.items()
        }

    selected = dict.fromkeys(CLASS_NAMES, "base")

    def total(selection: dict[str, str]) -> tuple[int, int, int]:
        return tuple(
            sum(choices[name][selection[name]][1][position] for name in CLASS_NAMES)
            for position in range(3)
        )

    for _iteration in range(5):
        changed = False
        for name in CLASS_NAMES:
            best_key = selected[name]
            best_score = f1(total(selected))
            for key in choices[name]:
                candidate = dict(selected)
                candidate[name] = key
                candidate_score = f1(total(candidate))
                if candidate_score > best_score + 1e-6:
                    best_key = key
                    best_score = candidate_score
            if best_key != selected[name]:
                selected[name] = best_key
                changed = True
        if not changed:
            break

    fusion_rules: dict[str, dict[str, Any]] = {}
    for name, selection in selected.items():
        mode, separator, raw_radius = selection.partition(":")
        fusion_rules[name] = {
            "mode": mode,
            "radiusFrames": int(raw_radius) if separator else 0,
        }
    original_counts = aggregate_base_counts(
        references, base_events, dict.fromkeys(CLASS_NAMES, 0)
    )
    aligned_counts = total(dict.fromkeys(CLASS_NAMES, "base"))
    fused_counts = total(selected)
    evidence = {
        "v19Original": score_payload(original_counts),
        "alignedV19Base": score_payload(aligned_counts),
        "outOfFoldFusion": score_payload(fused_counts),
        "selectedModes": selected,
    }
    return base_shifts, fusion_rules, evidence


def aggregate_base_counts(
    references: list[list[list[int]]],
    base_events: list[list[tuple[int, str]]],
    shifts: dict[str, int],
) -> tuple[int, int, int]:
    total = [0, 0, 0]
    for class_index, name in enumerate(CLASS_NAMES):
        counts = score_event_lists(
            references,
            class_index,
            {
                index: class_lists(events, name, shifts[name])
                for index, events in enumerate(base_events)
            },
        )
        for position in range(3):
            total[position] += counts[position]
    return tuple(total)


def exact_out_of_fold_evidence(
    tracks: list[dict[str, Any]],
    base_root: Path,
    stacker_events: dict[int, list[tuple[int, str]]],
    base_shifts: dict[str, int],
    fusion_rules: dict[str, dict[str, Any]],
    frame_seconds: float,
) -> dict[str, Any]:
    rules = {
        name: EventFusionRule(
            mode=rule["mode"],
            radius_seconds=int(rule["radiusFrames"]) * frame_seconds,
        )
        for name, rule in fusion_rules.items()
    }
    references: list[list[tuple[float, str]]] = []
    original: list[list[tuple[float, str]]] = []
    aligned: list[list[tuple[float, str]]] = []
    fused: list[list[tuple[float, str]]] = []
    for index, track in enumerate(tracks):
        raw = json.loads(
            (base_root / f"{track['rwcId']}.json").read_text(encoding="utf-8")
        )
        baseline = sorted(
            (float(hit["onsetSeconds"]), str(hit["instrument"])) for hit in raw["hits"]
        )
        aligned_events = sorted(
            (
                onset + base_shifts[instrument] * frame_seconds,
                instrument,
            )
            for onset, instrument in baseline
            if 0
            <= onset + base_shifts[instrument] * frame_seconds
            < float(track["clipDurationSeconds"])
        )
        stacker = [
            (frame * frame_seconds, instrument)
            for frame, instrument in stacker_events[index]
        ]
        references.append(reference_events_from_track(track))
        original.append(baseline)
        aligned.append(aligned_events)
        fused.append(fuse_event_streams(aligned_events, stacker, rules))
    return {
        "matching": "exact seconds using the release benchmark scorer",
        "v19Original": aggregate_scores(references, original),
        "alignedV19Base": aggregate_scores(references, aligned),
        "outOfFoldFusion": aggregate_scores(references, fused),
    }


def counts_payload(counts: tuple[int, int, int]) -> dict[str, int]:
    return {"tp": counts[0], "fp": counts[1], "fn": counts[2]}


def score_payload(counts: tuple[int, int, int]) -> dict[str, float | int]:
    return {"f1": f1(counts), **counts_payload(counts)}


def main() -> int:
    import torch

    args = parse_args()
    if args.epochs < 1 or args.folds < 2:
        raise ValueError(
            "epochs and folds must be positive; folds must be at least two"
        )
    repository = args.repository.resolve(strict=True)
    data_root = resolve(repository, args.data_root)
    probability_root = resolve(repository, args.probability_root)
    base_root = resolve(repository, args.base_root)
    checkpoint_path = resolve(repository, args.checkpoint, strict=False)
    config_path = resolve(repository, args.config, strict=False)
    evidence_path = resolve(repository, args.evidence, strict=False)
    manifest_path, manifest = load_and_validate_manifest(data_root)
    tracks = manifest["tracks"]
    features, targets, references, base_events, frame_seconds = load_inputs(
        probability_root, base_root, tracks
    )
    device = choose_device(args.device)
    torch.set_num_threads(4)

    out_of_fold_probabilities: dict[int, np.ndarray] = {}
    fold_evidence: list[dict[str, Any]] = []
    for fold in range(args.folds):
        training = [index for index in range(len(tracks)) if index % args.folds != fold]
        validation = [
            index for index in range(len(tracks)) if index % args.folds == fold
        ]
        model, mean, standard_deviation, loss = train_model(
            features,
            targets,
            training,
            epochs=args.epochs,
            seed=args.seed + fold,
            device=device,
        )
        training_probabilities = infer(
            model,
            features,
            training,
            mean,
            standard_deviation,
            device=device,
        )
        rules = tune_decoder(training_probabilities, references, training)
        out_of_fold_probabilities.update(
            infer(
                model,
                features,
                validation,
                mean,
                standard_deviation,
                device=device,
            )
        )
        fold_evidence.append(
            {
                "fold": fold,
                "trainingTracks": len(training),
                "validationTracks": len(validation),
                "finalTrainingLoss": loss,
                "decoderRules": rules,
            }
        )
        print(json.dumps({"fold": fold, "status": "complete"}), flush=True)

    out_of_fold_events: dict[int, list[tuple[int, str]]] = {}
    for fold, fold_data in enumerate(fold_evidence):
        validation = [
            index for index in range(len(tracks)) if index % args.folds == fold
        ]
        out_of_fold_events.update(
            decode(out_of_fold_probabilities, fold_data["decoderRules"], validation)
        )
    base_shifts, fusion_rules, cross_validation = optimize_fusion(
        references, base_events, out_of_fold_events
    )
    cross_validation["exactSecondDomain"] = exact_out_of_fold_evidence(
        tracks,
        base_root,
        out_of_fold_events,
        base_shifts,
        fusion_rules,
        frame_seconds,
    )

    all_indices = list(range(len(tracks)))
    final_model, mean, standard_deviation, final_loss = train_model(
        features,
        targets,
        all_indices,
        epochs=args.epochs,
        seed=args.seed,
        device=device,
    )
    final_probabilities = infer(
        final_model,
        features,
        all_indices,
        mean,
        standard_deviation,
        device=device,
    )
    final_decoder = tune_decoder(final_probabilities, references, all_indices)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_checkpoint = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
    torch.save(
        {
            "schemaVersion": 1,
            "modelVersion": "rwc-temporal-stacker-v20-research",
            "model": final_model.state_dict(),
            "normalizationMean": torch.from_numpy(mean),
            "normalizationStandardDeviation": torch.from_numpy(standard_deviation),
            "inputSize": features[0].shape[1],
            "hiddenSizes": (256, 128),
            "dropout": 0.15,
        },
        temporary_checkpoint,
    )
    temporary_checkpoint.replace(checkpoint_path)
    checkpoint_hash = sha256(checkpoint_path)
    config = {
        "schemaVersion": 1,
        "modelVersion": "rwc-temporal-stacker-v20-research",
        "productionApproved": False,
        "checkpoint": {
            "path": str(checkpoint_path.relative_to(repository)),
            "sha256": checkpoint_hash,
        },
        "features": {
            "sourceOrder": list(DEFAULT_SOURCE_ORDER),
            "offsetFrames": list(OFFSETS),
            "clipEpsilon": 1e-5,
            "frameSeconds": frame_seconds,
        },
        "training": {
            "corpus": "RWC Popular first 50 opened development songs",
            "corpusLicense": "CC BY-NC 4.0",
            "selectionManifestSha256": sha256(manifest_path),
            "trackCount": len(tracks),
            "folds": args.folds,
            "epochs": args.epochs,
            "seed": args.seed,
            "finalTrainingLoss": final_loss,
        },
        "baseOnsetShiftFrames": base_shifts,
        "stackerDecoderRules": {
            name: {
                key: value
                for key, value in rule.items()
                if key in {"threshold", "peakDistanceFrames", "onsetShiftFrames"}
            }
            for name, rule in final_decoder.items()
        },
        "fusionRules": fusion_rules,
        "developmentEvidence": cross_validation,
        "limitations": [
            "This stacker is trained and calibrated on CC BY-NC RWC references.",
            "It is research-only and cannot be deployed in the paid product.",
            "The 39-song RWC remainder was previously opened by v19 and is secondary evidence only.",
        ],
    }
    write_json(config_path, config)
    evidence = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "configurationSha256": sha256(config_path),
        "checkpointSha256": checkpoint_hash,
        "device": device,
        "crossValidation": cross_validation,
        "folds": fold_evidence,
        "finalDecoder": final_decoder,
    }
    write_json(evidence_path, evidence)
    print(
        json.dumps(
            {
                "config": str(config_path),
                "checkpoint": str(checkpoint_path),
                "evidence": str(evidence_path),
                "outOfFoldF1": cross_validation["outOfFoldFusion"]["f1"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
