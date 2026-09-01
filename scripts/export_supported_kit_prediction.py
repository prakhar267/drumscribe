#!/usr/bin/env python3
"""Export auditable notation from a frozen supported-kit checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from build_supported_kit_corpus import _events
from drumscribe_ml.training import (
    TRAINING_CLASSES,
    TrainingConfig,
    _apply_family_competition,
    _match_frames,
    _peak_frames,
    _training_device,
    build_model,
)
from drumscribe_music import DefaultQuantizer, RawDrumHit
from drumscribe_music.exporters import write_midi, write_musicxml, write_pdf


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--prepared-dataset", type=Path, required=True)
    parser.add_argument("--song-index", type=int, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--prediction-name", default="prediction")
    args = parser.parse_args()

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - requires training extra
        raise RuntimeError("install the ML training extra before exporting") from exc

    prepared_path = args.prepared_dataset.resolve(strict=True)
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    records = prepared.get("records", [])
    if len(records) != 1 or records[0].get("split") != "test":
        raise ValueError("export requires exactly one frozen test record")
    if prepared.get("configuration", {}).get("startIndex") != args.song_index:
        raise ValueError("song-index does not match the prepared dataset")
    record = records[0]
    output = prepared_path.parent
    if not args.prediction_name or "/" in args.prediction_name:
        raise ValueError("prediction-name must be a non-empty directory name")
    prediction = output / args.prediction_name
    if prediction.exists():
        raise FileExistsError(prediction)
    prediction.mkdir()

    checkpoint_path = args.checkpoint.resolve(strict=True)
    state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    config = TrainingConfig(**state["configuration"])
    thresholds = state.get("validationThresholds", {})
    peak_distances = state.get("validationPeakDistances", {})
    if set(thresholds) != {instrument.value for instrument in TRAINING_CLASSES}:
        raise ValueError("checkpoint does not contain a complete frozen decoder")

    feature_cache = np.load(record["featurePath"])
    features = feature_cache["features"].astype(np.float32)
    sample_rate = int(feature_cache["sample_rate"])
    hop_length = int(feature_cache["hop_length"])
    device = _training_device(torch, args.device)
    model = build_model(
        config,
        mel_bands=int(features.shape[1]),
        class_count=len(TRAINING_CLASSES),
    ).to(device)
    model.load_state_dict(state["model"])
    model.eval()
    with torch.no_grad():
        onset_logits, velocity_output = model(
            torch.from_numpy(features)[None].to(device)
        )
    probabilities = torch.sigmoid(onset_logits)[0].cpu().numpy()
    probabilities = _apply_family_competition(probabilities)
    velocities = velocity_output[0].cpu().numpy()

    annotation = json.loads(Path(record["annotationPath"]).read_text(encoding="utf-8"))
    references_by_class = {instrument.value: [] for instrument in TRAINING_CLASSES}
    for event in annotation["events"]:
        references_by_class[event["instrument"]].append(
            round(float(event["onsetSeconds"]) * sample_rate / hop_length)
        )

    raw_hits: list[RawDrumHit] = []
    counts = [0, 0, 0]
    per_class: dict[str, dict[str, float | int]] = {}
    for class_index, instrument in enumerate(TRAINING_CLASSES):
        predicted_frames = _peak_frames(
            probabilities[:, class_index],
            threshold=float(thresholds[instrument.value]),
            minimum_distance_frames=int(peak_distances[instrument.value]),
        )
        true_positive, false_positive, false_negative = _match_frames(
            references_by_class[instrument.value],
            predicted_frames,
            tolerance=config.onset_tolerance_frames,
        )
        counts[0] += true_positive
        counts[1] += false_positive
        counts[2] += false_negative
        denominator = 2 * true_positive + false_positive + false_negative
        per_class[instrument.value] = {
            "truePositive": true_positive,
            "falsePositive": false_positive,
            "falseNegative": false_negative,
            "f1": 2 * true_positive / denominator if denominator else 0.0,
        }
        for frame in predicted_frames:
            raw_hits.append(
                RawDrumHit(
                    instrument_class=instrument,
                    onset_seconds=frame * hop_length / sample_rate,
                    velocity=max(
                        1, min(127, round(float(velocities[frame, class_index]) * 127))
                    ),
                    confidence=float(probabilities[frame, class_index]),
                    metadata={"provider": config.model_version, "frame": frame},
                )
            )
    raw_hits.sort(key=lambda hit: (hit.onset_seconds, hit.instrument_class.value))

    tempo, reference_events = _events(args.song_index)
    predicted_events = DefaultQuantizer().quantize(raw_hits, tempo)
    if not (output / "reference.mid").exists():
        write_midi(output / "reference.mid", reference_events, tempo)
    if not (output / "reference.musicxml").exists():
        write_musicxml(
            output / "reference.musicxml",
            reference_events,
            tempo,
            title=f"{args.title} - Reference",
            artist="DrumScribe",
        )
    if not (output / "reference.pdf").exists():
        write_pdf(
            output / "reference.pdf",
            reference_events,
            tempo,
            title=f"{args.title} - Reference",
            artist="DrumScribe",
        )
    write_midi(prediction / "predicted.mid", predicted_events, tempo)
    write_musicxml(
        prediction / "predicted.musicxml",
        predicted_events,
        tempo,
        title=f"{args.title} - Prediction",
        artist="DrumScribe",
    )
    write_pdf(
        prediction / "predicted.pdf",
        predicted_events,
        tempo,
        title=f"{args.title} - Prediction",
        artist="DrumScribe",
    )
    (prediction / "predicted-events.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "modelVersion": config.model_version,
                "checkpointSha256": _sha256(checkpoint_path),
                "sourceAudioSha256": _sha256(Path(record["audioPath"])),
                "rawHits": [
                    {
                        "instrument": hit.instrument_class.value,
                        "onsetSeconds": hit.onset_seconds,
                        "velocity": hit.velocity,
                        "confidence": hit.confidence,
                    }
                    for hit in raw_hits
                ],
                "events": [event.as_dict() for event in predicted_events],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    true_positive, false_positive, false_negative = counts
    denominator = 2 * true_positive + false_positive + false_negative
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    report = {
        "schemaVersion": 1,
        "title": args.title,
        "songIndex": args.song_index,
        "checkpointSha256": _sha256(checkpoint_path),
        "referenceEvents": true_positive + false_negative,
        "predictedEvents": true_positive + false_positive,
        "eventMicroAtTolerance": {
            "toleranceFrames": config.onset_tolerance_frames,
            "toleranceMilliseconds": config.onset_tolerance_frames
            * hop_length
            / sample_rate
            * 1000,
            "truePositive": true_positive,
            "falsePositive": false_positive,
            "falseNegative": false_negative,
            "precision": precision,
            "recall": recall,
            "f1": 2 * true_positive / denominator if denominator else 0.0,
        },
        "perClass": per_class,
        "postTestTuning": False,
    }
    report_name = (
        "export-report.json"
        if args.prediction_name == "prediction"
        else f"{args.prediction_name}-export-report.json"
    )
    (output / report_name).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
