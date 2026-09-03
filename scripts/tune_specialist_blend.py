#!/usr/bin/env python3
"""Measure whether a new checkpoint complements the frozen production stack.

This is a validation-only model-selection utility.  It caches the exact v16
stack output and the candidate checkpoint output, searches bounded post-stack
blends, and writes evidence that can be checked on a separate frozen test set.
It never reads test labels.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_ml.ensemble import StackedEnsembleConfig, blend_stacked_probabilities
from drumscribe_ml.training import (
    TRAINING_CLASSES,
    TrainingConfig,
    _calibration_peak_f1,
    _calibration_peak_tracks,
    _load_training_record,
    _match_frames,
    _peak_frames,
    build_model,
)

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from run_competitive_drum_benchmark import CHECKPOINTS, load_models, sha256

DEFAULT_CONFIG = Path("ml/configs/groove-stacked-articulation-v16.json")
DEFAULT_PREPARED = Path(
    "data/licensed-corpus/groove-full-articulation-overlay-v2/prepared-dataset.json"
)
DEFAULT_CANDIDATE = Path(
    "data/licensed-corpus/experiments/"
    "groove-egmd-weak-class-specialist-v17/checkpoint-0015.pt"
)
DEFAULT_OUTPUT = Path(
    "output/articulation-competition-v17-2026-09-04/specialist-blend-search.json"
)
DEFAULT_CACHE = Path(
    "output/articulation-competition-v17-2026-09-04/specialist-blend-cache.npz"
)
ALPHAS = tuple(float(value) for value in np.linspace(0, 1, 21))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--candidate-checkpoint", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
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


def load_candidate(path: Path, *, mel_bands: int, device: str) -> Any:
    import torch

    state = torch.load(path, map_location="cpu", weights_only=True)
    configuration = TrainingConfig(**state["configuration"])
    model = build_model(
        configuration,
        mel_bands=mel_bands,
        class_count=len(TRAINING_CLASSES),
    ).to(device)
    model.load_state_dict(state["model"])
    model.eval()
    return model


def probability_logit(probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    return np.log(clipped) - np.log1p(-clipped)


def blend(
    baseline: np.ndarray,
    candidate: np.ndarray,
    *,
    strategy: str,
    alpha: float,
) -> np.ndarray:
    if strategy == "convex":
        return (1 - alpha) * baseline + alpha * candidate
    if strategy == "logit":
        combined = (1 - alpha) * probability_logit(baseline)
        combined += alpha * probability_logit(candidate)
        return 1 / (1 + np.exp(-np.clip(combined, -30, 30)))
    raise ValueError(f"unsupported blend strategy: {strategy}")


def threshold_candidates(baseline: float) -> np.ndarray:
    values = {float(value) for value in np.linspace(0.50, 0.9995, 101)}
    values.update(float(value) for value in np.linspace(0.90, 0.9995, 101))
    values.add(float(baseline))
    return np.asarray(sorted(values), dtype=np.float64)


def score_fixed(
    evaluated: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
    *,
    class_index: int,
    probability: Callable[[np.ndarray, np.ndarray], np.ndarray],
    threshold: float,
    peak_distance: int,
    tolerance: int,
) -> dict[str, float | int]:
    tp = fp = fn = 0
    for baseline, candidate, targets in evaluated:
        references = np.flatnonzero(targets[:, class_index] > 0).tolist()
        predictions = _peak_frames(
            probability(baseline[:, class_index], candidate[:, class_index]),
            threshold=threshold,
            minimum_distance_frames=peak_distance,
        )
        matched = _match_frames(references, predictions, tolerance=tolerance)
        tp += matched[0]
        fp += matched[1]
        fn += matched[2]
    denominator = 2 * tp + fp + fn
    return {
        "f1": 2 * tp / denominator if denominator else 0.0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def best_calibration(
    evaluated: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
    *,
    class_index: int,
    probability: Callable[[np.ndarray, np.ndarray], np.ndarray],
    thresholds: np.ndarray,
    peak_distances: tuple[int, ...],
    tolerance: int,
) -> dict[str, float | int]:
    calibration = [
        (
            probability(baseline[:, class_index], candidate[:, class_index])[:, None],
            targets[:, class_index : class_index + 1],
        )
        for baseline, candidate, targets in evaluated
    ]
    scored: list[tuple[float, float, int]] = []
    for peak_distance in peak_distances:
        tracks = _calibration_peak_tracks(
            calibration,
            class_index=0,
            peak_distance_frames=peak_distance,
        )
        for threshold in thresholds:
            f1 = _calibration_peak_f1(
                tracks,
                threshold=float(threshold),
                tolerance_frames=tolerance,
            )
            scored.append((f1, float(threshold), peak_distance))
    f1, threshold, peak_distance = max(
        scored,
        key=lambda item: (item[0], -abs(item[1] - 0.5), -item[2]),
    )
    counts = score_fixed(
        evaluated,
        class_index=class_index,
        probability=probability,
        threshold=threshold,
        peak_distance=peak_distance,
        tolerance=tolerance,
    )
    return {
        **counts,
        "threshold": threshold,
        "peakDistanceFrames": peak_distance,
        "f1": f1,
    }


def aggregate(per_class: dict[str, dict[str, Any]]) -> dict[str, float | int]:
    rows = list(per_class.values())
    tp = sum(int(row["tp"]) for row in rows)
    fp = sum(int(row["fp"]) for row in rows)
    fn = sum(int(row["fn"]) for row in rows)
    denominator = 2 * tp + fp + fn
    return {
        "supportedMacroF1": sum(float(row["f1"]) for row in rows) / len(rows),
        "microF1": 2 * tp / denominator if denominator else 0.0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def main() -> int:
    args = parse_args()
    repository = args.repository.resolve(strict=True)
    config_path = resolve(repository, args.config)
    prepared_path = resolve(repository, args.prepared)
    candidate_path = resolve(repository, args.candidate_checkpoint)
    output_path = resolve(repository, args.output, strict=False)
    cache_path = resolve(repository, args.cache, strict=False)
    config = StackedEnsembleConfig.load(config_path)
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    records = [
        record for record in prepared["records"] if record["split"] == "validation"
    ]
    if not records:
        raise RuntimeError("prepared dataset has no validation records")

    metadata = {
        "configSha256": sha256(config_path),
        "preparedDatasetSha256": sha256(prepared_path),
        "candidateCheckpointSha256": sha256(candidate_path),
        "recordCount": len(records),
        "probabilityDtype": "float64",
    }
    evaluated: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    if cache_path.exists():
        with np.load(cache_path, allow_pickle=False) as cache:
            cached_metadata = json.loads(str(cache["metadata"].item()))
            if cached_metadata != metadata:
                raise RuntimeError("specialist blend cache metadata mismatch")
            for sequence in range(len(records)):
                evaluated.append(
                    (
                        cache[f"baseline_{sequence:03d}"],
                        cache[f"candidate_{sequence:03d}"],
                        cache[f"targets_{sequence:03d}"].astype(np.float32),
                    )
                )
    else:
        device = choose_device(args.device)
        checkpoint_paths = {
            name: resolve(repository, CHECKPOINTS[name]) for name in config.models
        }
        with np.load(Path(records[0]["featurePath"]), allow_pickle=False) as arrays:
            mel_bands = int(arrays["features"].shape[1])
        models = load_models(config, checkpoint_paths, mel_bands, device)
        candidate_model = load_candidate(
            candidate_path, mel_bands=mel_bands, device=device
        )

        import torch

        with torch.no_grad():
            for sequence, record in enumerate(records, 1):
                features, targets, _ = _load_training_record(record)
                tensor = torch.from_numpy(features)[None].to(device)
                probabilities_by_model = {
                    name: torch.sigmoid(model(tensor)[0])[0].cpu().numpy()
                    for name, model in models.items()
                }
                baseline = blend_stacked_probabilities(
                    probabilities_by_model, config.rules
                )
                candidate = torch.sigmoid(candidate_model(tensor)[0])[0].cpu().numpy()
                evaluated.append((baseline, candidate, targets))
                print(
                    json.dumps({"sequence": sequence, "records": len(records)}),
                    flush=True,
                )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_payload: dict[str, np.ndarray] = {
            "metadata": np.asarray(json.dumps(metadata, sort_keys=True))
        }
        for sequence, (baseline, candidate, targets) in enumerate(evaluated):
            cache_payload[f"baseline_{sequence:03d}"] = baseline.astype(np.float64)
            cache_payload[f"candidate_{sequence:03d}"] = candidate.astype(np.float64)
            cache_payload[f"targets_{sequence:03d}"] = targets.astype(np.uint8)
        np.savez_compressed(cache_path, **cache_payload)

    baseline_rows: dict[str, dict[str, Any]] = {}
    selected_rows: dict[str, dict[str, Any]] = {}
    searches: dict[str, Any] = {}
    for class_index, instrument in enumerate(TRAINING_CLASSES):
        support = sum(int(targets[:, class_index].sum()) for _, _, targets in evaluated)
        if not support:
            continue
        rule = config.rules[instrument.value]
        identity = lambda baseline, candidate: baseline
        baseline_score = score_fixed(
            evaluated,
            class_index=class_index,
            probability=identity,
            threshold=rule.threshold,
            peak_distance=rule.peak_distance_frames,
            tolerance=config.onset_tolerance_frames,
        )
        baseline_row = {
            **baseline_score,
            "strategy": "baseline",
            "alpha": 0.0,
            "threshold": rule.threshold,
            "peakDistanceFrames": rule.peak_distance_frames,
            "support": support,
        }
        candidates = [baseline_row]
        distances = tuple(
            sorted(
                {
                    rule.peak_distance_frames,
                    max(1, rule.peak_distance_frames - 1),
                    rule.peak_distance_frames + 1,
                }
            )
        )
        thresholds = threshold_candidates(rule.threshold)
        for strategy in ("convex", "logit"):
            for alpha in ALPHAS[1:]:
                probability = lambda baseline, candidate, s=strategy, a=alpha: blend(
                    baseline, candidate, strategy=s, alpha=a
                )
                calibrated = best_calibration(
                    evaluated,
                    class_index=class_index,
                    probability=probability,
                    thresholds=thresholds,
                    peak_distances=distances,
                    tolerance=config.onset_tolerance_frames,
                )
                candidates.append(
                    {
                        **calibrated,
                        "strategy": strategy,
                        "alpha": alpha,
                        "support": support,
                    }
                )
        ranked = sorted(
            candidates,
            key=lambda row: (
                float(row["f1"]),
                -float(row["alpha"]),
                -abs(float(row["threshold"]) - rule.threshold),
            ),
            reverse=True,
        )
        best = ranked[0]
        baseline_rows[instrument.value] = baseline_row
        selected_rows[instrument.value] = best
        searches[instrument.value] = {
            "baseline": baseline_row,
            "best": best,
            "deltaF1": float(best["f1"]) - float(baseline_row["f1"]),
            "topCandidates": ranked[:5],
        }
        print(
            json.dumps(
                {
                    "instrument": instrument.value,
                    "baselineF1": baseline_row["f1"],
                    "bestF1": best["f1"],
                    "strategy": best["strategy"],
                    "alpha": best["alpha"],
                }
            ),
            flush=True,
        )

    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "split": "validation",
        "recordCount": len(records),
        "modelVersion": config.model_version,
        "candidateCheckpoint": str(candidate_path),
        **metadata,
        "searchSpace": {
            "strategies": ["convex", "logit"],
            "alphas": ALPHAS,
            "thresholdCandidateCount": "up to 203 including the existing threshold",
            "peakDistanceRadiusFrames": 1,
        },
        "baseline": aggregate(baseline_rows),
        "bestIndependentPerClass": aggregate(selected_rows),
        "perClass": searches,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(output_path),
                "baseline": report["baseline"],
                "bestIndependentPerClass": report["bestIndependentPerClass"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
