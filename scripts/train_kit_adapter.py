#!/usr/bin/env python3
"""Train the compact kit-adaptive detector from an explicitly unsealed dev song.

This script is intentionally unable to read a sealed benchmark directory.  The
input must contain the first metal benchmark after it has been declared
development data.  A later song/recording chain is required for honest testing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from drumscribe_ml.kit_adapter import (
    DEFAULT_FLUX_QUANTILE,
    DEFAULT_PEAK_DISTANCE_FRAMES,
    MODEL_SCHEMA_VERSION,
    KitAdapterModel,
    candidate_vectors,
    dense_transient_frames,
    write_manifest,
)
from drumscribe_ml.training import TRAINING_CLASSES

SEED = 2_026_090_1
TOLERANCE_FRAMES = 5


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_development_examples(
    benchmark: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Path]:
    result_path = benchmark / "benchmark-result.json"
    reference_path = benchmark / "reference-events.json"
    feature_path = benchmark / "prediction" / "drum-stem-features.npz"
    if not all(path.is_file() for path in (result_path, reference_path, feature_path)):
        raise FileNotFoundError(
            "development benchmark needs its result, reference events, and prediction features"
        )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("benchmark") != "sealed-original-metal-v1":
        raise ValueError(
            "only the completed v1 benchmark may become adapter development data"
        )
    if result.get("testProtocol", {}).get("postTestTuning") is not False:
        raise ValueError(
            "the source benchmark protocol is not an untouched completed run"
        )

    with np.load(feature_path, allow_pickle=False) as arrays:
        features = np.asarray(arrays["features"], dtype=np.float32)
    frames = dense_transient_frames(
        features,
        flux_quantile=DEFAULT_FLUX_QUANTILE,
        minimum_distance_frames=DEFAULT_PEAK_DISTANCE_FRAMES,
    )
    events = json.loads(reference_path.read_text(encoding="utf-8"))["events"]
    class_index = {
        instrument.value: index for index, instrument in enumerate(TRAINING_CLASSES)
    }
    labels = np.zeros((len(frames), len(TRAINING_CLASSES)), dtype=np.float32)
    reference_frames = [
        (
            round(float(event["onsetSeconds"]) * 22_050 / 220),
            class_index[str(event["instrument"])],
        )
        for event in events
    ]
    for row, frame in enumerate(frames):
        for reference_frame, instrument_index in reference_frames:
            if abs(reference_frame - frame) <= TOLERANCE_FRAMES:
                labels[row, instrument_index] = 1

    # Five adjacent alignments make the model robust to the detector selecting a
    # neighboring spectral-flux frame on a different recording chain.
    variants = []
    variant_labels = []
    variant_groups = []
    for shift in (-2, -1, 0, 1, 2):
        variants.append(
            candidate_vectors(features, [frame + shift for frame in frames])
        )
        variant_labels.append(labels)
        variant_groups.append(np.asarray(frames, dtype=np.int32))
    vectors = np.concatenate(variants).astype(np.float32)
    expanded_labels = np.concatenate(variant_labels).astype(np.float32)
    groups = np.concatenate(variant_groups)
    return vectors, expanded_labels, groups, labels, reference_path


def _network(torch, input_width: int, class_count: int):
    class Network(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.network = torch.nn.Sequential(
                torch.nn.Linear(input_width, 320),
                torch.nn.LayerNorm(320),
                torch.nn.GELU(approximate="tanh"),
                torch.nn.Dropout(0.15),
                torch.nn.Linear(320, 160),
                torch.nn.GELU(approximate="tanh"),
                torch.nn.Linear(160, class_count),
            )

        def forward(self, values):
            return self.network(values)

    return Network()


def _device(torch, requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if bool(getattr(torch.backends, "mps", None)) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _fit(
    torch,
    vectors: np.ndarray,
    labels: np.ndarray,
    indices: np.ndarray,
    *,
    device: str,
    steps: int,
    seed: int,
):
    torch.manual_seed(seed)
    model = _network(torch, vectors.shape[1], labels.shape[1]).to(device)
    positives = labels[indices].sum(axis=0)
    positive_weights = np.clip(
        (len(indices) - positives) / np.maximum(positives, 1),
        1,
        24,
    ).astype(np.float32)
    loss_function = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.from_numpy(positive_weights).to(device)
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.00025, weight_decay=0.001)
    rng = np.random.default_rng(seed)
    model.train()
    for _ in range(steps):
        selected = rng.choice(indices, size=256, replace=True)
        noise = rng.normal(0, 0.035, (len(selected), vectors.shape[1])).astype(
            np.float32
        )
        batch = vectors[selected] + noise
        optimizer.zero_grad()
        logits = model(torch.from_numpy(batch).to(device))
        loss = loss_function(logits, torch.from_numpy(labels[selected]).to(device))
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
        optimizer.step()
    return model


def _probabilities(torch, model, vectors: np.ndarray, device: str) -> np.ndarray:
    model.eval()
    chunks = []
    with torch.no_grad():
        for start in range(0, len(vectors), 512):
            logits = model(torch.from_numpy(vectors[start : start + 512]).to(device))
            chunks.append(torch.sigmoid(logits).cpu().numpy())
    return np.concatenate(chunks) if chunks else np.empty((0, len(TRAINING_CLASSES)))


def _thresholds(probabilities: np.ndarray, labels: np.ndarray) -> np.ndarray:
    selected = []
    for index in range(labels.shape[1]):
        truth = labels[:, index] > 0
        best = (-1.0, 0.5)
        for threshold in np.linspace(0.03, 0.97, 95):
            predicted = probabilities[:, index] >= threshold
            true_positive = int(np.sum(predicted & truth))
            false_positive = int(np.sum(predicted & ~truth))
            false_negative = int(np.sum(~predicted & truth))
            denominator = 2 * true_positive + false_positive + false_negative
            f1 = 2 * true_positive / denominator if denominator else 0.0
            candidate = (f1, -abs(float(threshold) - 0.5), float(threshold))
            incumbent = (best[0], -abs(best[1] - 0.5), best[1])
            if candidate > incumbent:
                best = (f1, float(threshold))
        selected.append(best[1])
    return np.asarray(selected, dtype=np.float32)


def _export(
    torch,
    model,
    output: Path,
    *,
    mean: np.ndarray,
    std: np.ndarray,
    thresholds: np.ndarray,
    model_version: str,
    reference_sha256: str,
    flux_quantile: float = DEFAULT_FLUX_QUANTILE,
    peak_distance_frames: int = DEFAULT_PEAK_DISTANCE_FRAMES,
    class_peak_distance_frames: np.ndarray | None = None,
) -> None:
    state = model.cpu().state_dict()
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        schema_version=np.array(MODEL_SCHEMA_VERSION),
        model_version=np.array(model_version),
        classes=np.asarray([instrument.value for instrument in TRAINING_CLASSES]),
        thresholds=thresholds,
        feature_mean=mean,
        feature_std=std,
        w1=state["network.0.weight"].numpy(),
        b1=state["network.0.bias"].numpy(),
        layer_norm_weight=state["network.1.weight"].numpy(),
        layer_norm_bias=state["network.1.bias"].numpy(),
        w2=state["network.4.weight"].numpy(),
        b2=state["network.4.bias"].numpy(),
        w3=state["network.6.weight"].numpy(),
        b3=state["network.6.bias"].numpy(),
        flux_quantile=np.array(flux_quantile, dtype=np.float32),
        peak_distance_frames=np.array(peak_distance_frames, dtype=np.int32),
        class_peak_distance_frames=(
            np.ones(len(TRAINING_CLASSES), dtype=np.int32)
            if class_peak_distance_frames is None
            else class_peak_distance_frames.astype(np.int32)
        ),
        training_reference_sha256=np.array(reference_sha256),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-version", default="kit-adaptive-multilabel-v17")
    parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    parser.add_argument("--steps", type=int, default=1_600)
    args = parser.parse_args()
    if args.output.exists() or args.manifest.exists():
        raise FileExistsError("model output and manifest must be new files")

    try:
        import torch
    except ImportError as exc:
        raise SystemExit("training requires PyTorch") from exc

    vectors, labels, groups, base_labels, reference_path = _load_development_examples(
        args.development_benchmark.resolve(strict=True)
    )
    mean = vectors.mean(axis=0).astype(np.float32)
    std = (vectors.std(axis=0) + 1e-4).astype(np.float32)
    vectors = ((vectors - mean) / std).astype(np.float32)
    unique_groups = np.unique(groups)
    group_fold = {
        int(group): int(index % 4)
        for index, group in enumerate(
            np.random.default_rng(SEED).permutation(unique_groups)
        )
    }
    folds = np.asarray([group_fold[int(group)] for group in groups])
    device = _device(torch, args.device)

    out_of_fold = np.zeros_like(labels)
    fold_steps = max(500, args.steps // 2)
    all_indices = np.arange(len(vectors))
    for fold in range(4):
        train_indices = all_indices[folds != fold]
        validation_indices = all_indices[folds == fold]
        model = _fit(
            torch,
            vectors,
            labels,
            train_indices,
            device=device,
            steps=fold_steps,
            seed=SEED + fold,
        )
        out_of_fold[validation_indices] = _probabilities(
            torch, model, vectors[validation_indices], device
        )
    thresholds = _thresholds(out_of_fold, labels)

    final_model = _fit(
        torch,
        vectors,
        labels,
        all_indices,
        device=device,
        steps=args.steps,
        seed=SEED + 10,
    )
    _export(
        torch,
        final_model,
        args.output,
        mean=mean,
        std=std,
        thresholds=thresholds,
        model_version=args.model_version,
        reference_sha256=_sha256(reference_path),
    )
    model = KitAdapterModel.load(args.output)
    # Loading through the serving runtime is part of training acceptance.
    if model.model_version != args.model_version or len(base_labels) == 0:
        raise RuntimeError("exported kit-adapter checkpoint did not validate")
    write_manifest(args.output, args.manifest)
    print(
        json.dumps(
            {
                "model": str(args.output.resolve()),
                "manifest": str(args.manifest.resolve()),
                "modelVersion": args.model_version,
                "developmentCandidates": len(base_labels),
                "trainingExamples": len(vectors),
                "device": device,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
