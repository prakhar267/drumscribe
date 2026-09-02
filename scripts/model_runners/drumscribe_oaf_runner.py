#!/usr/bin/env python3
"""Run DrumScribe's clean-room supported-kit OaF checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel
from drumscribe_ml.training import (
    TRAINING_CLASSES,
    TrainingConfig,
    _apply_family_competition,
    _peak_frames,
    _training_device,
    build_model,
)

PROVIDER = "drumscribe-supported-kit-oaf-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_decoder(
    decoder: Path | None,
    *,
    checkpoint_sha256: str,
    checkpoint_state: dict[str, object],
) -> tuple[
    dict[str, float],
    dict[str, int],
    dict[str, int],
    dict[str, float],
    str,
    str | None,
]:
    class_names = {instrument.value for instrument in TRAINING_CLASSES}
    if decoder is None:
        thresholds = checkpoint_state.get("validationThresholds", {})
        peak_distances = checkpoint_state.get("validationPeakDistances", {})
        if set(thresholds) != class_names or set(peak_distances) != class_names:
            raise ValueError("checkpoint does not contain a complete frozen decoder")
        return (
            {name: float(value) for name, value in thresholds.items()},
            {name: int(value) for name, value in peak_distances.items()},
            dict.fromkeys(class_names, 0),
            dict.fromkeys(class_names, 0.0),
            str(checkpoint_state["configuration"]["model_version"]),
            None,
        )

    payload = json.loads(decoder.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        raise ValueError("decoder schemaVersion must be 1")
    if payload.get("checkpointSha256") != checkpoint_sha256:
        raise ValueError("decoder was calibrated for a different checkpoint")
    thresholds = payload.get("thresholds", {})
    peak_distances = payload.get("peakDistances", {})
    onset_shifts = payload.get("onsetShiftFrames", {})
    onset_offsets = payload.get("onsetOffsetSeconds", dict.fromkeys(class_names, 0.0))
    if any(
        set(values) != class_names
        for values in (thresholds, peak_distances, onset_shifts, onset_offsets)
    ):
        raise ValueError("decoder does not contain every supported instrument")
    return (
        {name: float(value) for name, value in thresholds.items()},
        {name: int(value) for name, value in peak_distances.items()},
        {name: int(value) for name, value in onset_shifts.items()},
        {name: float(value) for name, value in onset_offsets.items()},
        str(payload["modelVersion"]),
        _sha256(decoder),
    )


def transcribe(
    checkpoint: Path,
    source: Path,
    device: str,
    decoder: Path | None = None,
) -> dict[str, object]:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - requires the training extra
        raise RuntimeError(
            "install the ML training extra to run this checkpoint"
        ) from exc

    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    config = TrainingConfig(**state["configuration"])
    checkpoint_sha256 = _sha256(checkpoint)
    (
        thresholds,
        peak_distances,
        onset_shifts,
        onset_offsets,
        model_version,
        decoder_sha256,
    ) = _load_decoder(
        decoder,
        checkpoint_sha256=checkpoint_sha256,
        checkpoint_state=state,
    )

    with tempfile.TemporaryDirectory(prefix="drumscribe-oaf-") as directory:
        feature_path = Path(directory) / "features.npz"
        cache_log_mel(
            source,
            feature_path,
            PreparationConfig(
                seed="supported-kit-oaf-inference", augmentation_variants=0
            ),
        )
        with np.load(feature_path, allow_pickle=False) as arrays:
            features = np.asarray(arrays["features"], dtype=np.float32)
            sample_rate = int(arrays["sample_rate"])
            hop_length = int(arrays["hop_length"])

    selected_device = _training_device(torch, device)
    model = build_model(
        config,
        mel_bands=int(features.shape[1]),
        class_count=len(TRAINING_CLASSES),
    ).to(selected_device)
    model.load_state_dict(state["model"])
    model.eval()
    with torch.no_grad():
        onset_logits, velocity_output = model(
            torch.from_numpy(features)[None].to(selected_device)
        )
    probabilities = _apply_family_competition(
        torch.sigmoid(onset_logits)[0].cpu().numpy()
    )
    velocities = velocity_output[0].cpu().numpy()

    hits: list[dict[str, object]] = []
    for class_index, instrument in enumerate(TRAINING_CLASSES):
        frames = _peak_frames(
            probabilities[:, class_index],
            threshold=float(thresholds[instrument.value]),
            minimum_distance_frames=int(peak_distances[instrument.value]),
        )
        hits.extend(
            {
                "instrument": instrument.value,
                "onsetSeconds": round(
                    max(
                        0.0,
                        (frame + onset_shifts[instrument.value])
                        * hop_length
                        / sample_rate
                        + onset_offsets[instrument.value],
                    ),
                    6,
                ),
                "velocity": max(
                    1,
                    min(127, round(float(velocities[frame, class_index]) * 127)),
                ),
                "confidence": round(float(probabilities[frame, class_index]), 7),
            }
            for frame in frames
        )
    hits.sort(key=lambda item: (float(item["onsetSeconds"]), str(item["instrument"])))
    return {
        "schemaVersion": 1,
        "provider": PROVIDER,
        "modelVersion": model_version,
        "checkpointSha256": checkpoint_sha256,
        "decoderSha256": decoder_sha256,
        "hits": hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decoder", type=Path)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    payload = transcribe(
        args.checkpoint.resolve(strict=True),
        args.input.resolve(strict=True),
        args.device,
        args.decoder.resolve(strict=True) if args.decoder else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
