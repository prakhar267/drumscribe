#!/usr/bin/env python3
"""Run DrumScribe's licensed ADTOF + first-party recall fusion."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

REPOSITORY = Path(__file__).resolve().parents[2]
for source_root in (
    REPOSITORY / "scripts",
    REPOSITORY / "ml" / "src",
    REPOSITORY / "packages" / "music-engine" / "src",
):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from _midi_contract import write_hits_contract
from adtof_pytorch import (
    calculate_n_bins,
    create_frame_rnn_model,
    load_audio_for_model,
    load_pytorch_weights,
)
from adtof_pytorch.post_processing import NotePeakPickingProcessor
from adtof_runner import filter_rhythm_inconsistencies
from drumscribe_ml.ensemble import (
    StackedEnsembleConfig,
    decode_stacked_probabilities,
)
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel
from drumscribe_ml.training import TRAINING_CLASSES, _peak_frames
from run_competitive_drum_benchmark import (
    CHECKPOINTS,
    load_models,
    predict_stacked_probabilities,
)

PROVIDER = "drumscribe-recall-fusion-v2"
FAMILIES = ("KICK", "SNARE", "TOM", "HIHAT", "CYMBAL")
ADTOF_CLASS_INDEX = {family: index for index, family in enumerate(FAMILIES)}
FAMILY_BY_INSTRUMENT = {
    "KICK": "KICK",
    "SNARE": "SNARE",
    "CROSS_STICK": "SNARE",
    "HIGH_TOM": "TOM",
    "MID_TOM": "TOM",
    "LOW_TOM": "TOM",
    "FLOOR_TOM": "TOM",
    "CLOSED_HIHAT": "HIHAT",
    "OPEN_HIHAT": "HIHAT",
    "PEDAL_HIHAT": "HIHAT",
    "CRASH": "CYMBAL",
    "RIDE": "CYMBAL",
    "RIDE_BELL": "CYMBAL",
}
GENERIC_INSTRUMENT = {
    "KICK": "KICK",
    "SNARE": "SNARE",
    "TOM": "MID_TOM",
    "HIHAT": "CLOSED_HIHAT",
    "CYMBAL": "CRASH",
}


@dataclass(frozen=True, slots=True)
class Hit:
    instrument: str
    onset: float
    confidence: float

    @property
    def family(self) -> str:
        return FAMILY_BY_INSTRUMENT[self.instrument]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve(repository: Path, value: str) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else repository / path).resolve(strict=True)


def validate_config(config: dict[str, Any], repository: Path) -> None:
    if config.get("schemaVersion") != 1 or config.get("modelVersion") != PROVIDER:
        raise RuntimeError("recall-fusion config has an unsupported contract")
    if config.get("productionApproved") is not True:
        raise RuntimeError("recall-fusion config is not production approved")
    for component in config["components"].values():
        path = resolve(repository, str(component["path"]))
        if sha256(path) != str(component["sha256"]):
            raise RuntimeError(f"component hash mismatch: {path}")


def load_adtof_model(weights: Path, device: str) -> Any:
    model = create_frame_rnn_model(calculate_n_bins())
    model = load_pytorch_weights(model, str(weights), strict=False)
    return model.eval().to(device)


def adtof_activations(model: Any, audio: Path, device: str) -> np.ndarray:
    import torch

    model_input = load_audio_for_model(str(audio)).to(device)
    with torch.no_grad():
        return model(model_input).cpu().numpy()[0].astype(np.float32, copy=False)


def process_activation(
    activation: np.ndarray, rule: dict[str, Any]
) -> list[tuple[float, float]]:
    processor = NotePeakPickingProcessor(
        threshold=float(rule["threshold"]),
        pre_avg=float(rule["preAverageSeconds"]),
        post_avg=0.01,
        pre_max=float(rule.get("preMaximumSeconds", 0.02)),
        post_max=0.01,
        combine=float(rule.get("combineSeconds", 0.02)),
        fps=100,
    )
    times = [float(time) for time, _ in processor.process(activation)]
    moving_average = processor._moving_average(
        activation,
        round(processor.pre_avg * processor.fps),
        round(processor.post_avg * processor.fps),
    )
    residual = np.maximum(0.0, activation - moving_average)
    return [
        (time, min(1.0, max(0.0, float(residual[round(time * 100)]))))
        for time in times
    ]


def load_ensemble_probabilities(
    audio: Path,
    repository: Path,
    ensemble_config_path: Path,
    device: str,
) -> tuple[np.ndarray, float, StackedEnsembleConfig]:
    configuration = StackedEnsembleConfig.load(ensemble_config_path)
    with tempfile.TemporaryDirectory(prefix="drumscribe-recall-fusion-features-") as directory:
        feature_path = Path(directory) / "features.npz"
        cache_log_mel(
            audio,
            feature_path,
            PreparationConfig(seed="recall-fusion-v2-inference", augmentation_variants=0),
        )
        with np.load(feature_path, allow_pickle=False) as arrays:
            mel_bands = int(arrays["features"].shape[1])
        models = load_models(
            configuration,
            {
                name: (repository / CHECKPOINTS[name]).resolve(strict=True)
                for name in configuration.models
            },
            mel_bands,
            device,
        )
        probabilities, frame_seconds = predict_stacked_probabilities(
            feature_path,
            models,
            configuration,
            device,
            1_000_000.0,
        )
    return probabilities, frame_seconds, configuration


def ensemble_hits(
    probabilities: np.ndarray,
    frame_seconds: float,
    configuration: StackedEnsembleConfig,
) -> list[Hit]:
    decoded = decode_stacked_probabilities(
        probabilities,
        configuration.rules,
        family_conflict_margins=configuration.family_conflict_margins,
    )
    class_index = {
        instrument.value: index for index, instrument in enumerate(TRAINING_CLASSES)
    }
    return sorted(
        (
            Hit(
                instrument.value,
                frame * frame_seconds,
                float(probabilities[frame, class_index[instrument.value]]),
            )
            for instrument in TRAINING_CLASSES
            if instrument.value in FAMILY_BY_INSTRUMENT
            for frame in decoded[instrument.value]
        ),
        key=lambda hit: (hit.onset, hit.instrument),
    )


def near(onset: float, hits: list[Hit], tolerance: float) -> bool:
    return any(abs(onset - hit.onset) <= tolerance for hit in hits)


def merge_family_hits(base: list[Hit], additions: list[Hit], tolerance: float) -> list[Hit]:
    result = list(base)
    for addition in additions:
        nearby = [
            (abs(addition.onset - hit.onset), index, hit)
            for index, hit in enumerate(result)
            if hit.family == addition.family
            and abs(addition.onset - hit.onset) <= tolerance
        ]
        if nearby:
            _, index, existing = min(nearby)
            result[index] = replace(
                existing,
                onset=(existing.onset + addition.onset) / 2,
                confidence=max(existing.confidence, addition.confidence),
            )
        else:
            result.append(addition)
    return sorted(result, key=lambda hit: (hit.onset, hit.instrument))


def is_periodically_supported(
    onset: float,
    hits: list[Hit],
    family: str,
    *,
    tolerance: float,
    maximum_period: float,
) -> bool:
    family_times = [hit.onset for hit in hits if hit.family == family]
    left = [time for time in family_times if 0.08 <= onset - time <= maximum_period]
    right = [time for time in family_times if 0.08 <= time - onset <= maximum_period]
    return any(
        abs((onset - before) - (after - onset)) <= tolerance
        for before in left
        for after in right
    )


def family_indices(family: str) -> list[int]:
    return [
        index
        for index, instrument in enumerate(TRAINING_CLASSES)
        if FAMILY_BY_INSTRUMENT.get(instrument.value) == family
    ]


def best_family_instrument(
    family: str, probabilities: np.ndarray, frame: int
) -> tuple[str, float]:
    indices = family_indices(family)
    index = max(indices, key=lambda candidate: probabilities[frame, candidate])
    return TRAINING_CLASSES[index].value, float(probabilities[frame, index])


def recover_consensus_hits(
    hits: list[Hit],
    adtof: np.ndarray,
    ensemble: np.ndarray,
    frame_seconds: float,
    peak_rules: dict[str, dict[str, Any]],
    recovery_rules: dict[str, dict[str, Any]],
) -> tuple[list[Hit], int]:
    result = list(hits)
    recovered = 0
    for family, recovery in recovery_rules.items():
        class_index = ADTOF_CLASS_INDEX[family]
        adtof_rule = {
            **peak_rules[family],
            "threshold": float(recovery["adtofThreshold"]),
        }
        adtof_candidates = process_activation(adtof[:, class_index], adtof_rule)
        indices = family_indices(family)
        family_probability = ensemble[:, indices].max(axis=1)
        ensemble_frames = _peak_frames(
            family_probability,
            threshold=float(recovery["ensembleThreshold"]),
            minimum_distance_frames=3,
        )
        ensemble_times = [frame * frame_seconds for frame in ensemble_frames]
        for onset, confidence in adtof_candidates:
            family_hits = [hit for hit in result if hit.family == family]
            if near(onset, family_hits, 0.035):
                continue
            matches = [
                (abs(onset - time), frame, time)
                for frame, time in zip(ensemble_frames, ensemble_times, strict=True)
                if abs(onset - time) <= float(recovery["matchSeconds"])
            ]
            if not matches:
                continue
            if recovery.get("periodic") and not is_periodically_supported(
                onset,
                result,
                family,
                tolerance=float(recovery["periodToleranceSeconds"]),
                maximum_period=float(recovery["maximumPeriodSeconds"]),
            ):
                continue
            _, frame, ensemble_time = min(matches)
            instrument, ensemble_confidence = best_family_instrument(
                family, ensemble, frame
            )
            result.append(
                Hit(
                    instrument,
                    (onset + ensemble_time) / 2,
                    max(confidence, ensemble_confidence),
                )
            )
            result.sort(key=lambda hit: (hit.onset, hit.instrument))
            recovered += 1
    return result, recovered


def drum_only_fusion(
    adtof: np.ndarray,
    ensemble: np.ndarray,
    frame_seconds: float,
    configuration: StackedEnsembleConfig,
    rules: dict[str, Any],
) -> tuple[list[Hit], dict[str, int]]:
    hits = ensemble_hits(ensemble, frame_seconds, configuration)
    added_by_union = 0
    for family in rules["unionFamilies"]:
        class_index = ADTOF_CLASS_INDEX[family]
        additions = [
            Hit(GENERIC_INSTRUMENT[family], onset, confidence)
            for onset, confidence in process_activation(
                adtof[:, class_index], rules["adtofPeakRules"][family]
            )
        ]
        before = len(hits)
        hits = merge_family_hits(
            hits, additions, float(rules["unionToleranceSeconds"])
        )
        added_by_union += len(hits) - before
    hits, recovered = recover_consensus_hits(
        hits,
        adtof,
        ensemble,
        frame_seconds,
        rules["adtofPeakRules"],
        rules["consensusRecovery"],
    )
    return hits, {"unionAdded": added_by_union, "consensusRecovered": recovered}


def acoustic_precision_hits(
    adtof: np.ndarray, rules: dict[str, Any]
) -> list[Hit]:
    """Decode isolated acoustic drums without the electronic-kit specialist."""
    profile = rules["profiles"]["acoustic_precision"]
    latency = float(profile.get("latencyCompensationSeconds", 0.0))
    hits: list[Hit] = []
    for family in FAMILIES:
        class_index = ADTOF_CLASS_INDEX[family]
        rule = profile["peakRules"][family]
        for onset, confidence in process_activation(adtof[:, class_index], rule):
            frame = min(round(onset * 100), len(adtof) - 1)
            activation = float(adtof[frame, class_index])
            other_activation = float(np.delete(adtof[frame], class_index).max())
            if activation < float(rule.get("minimumActivation", 0.0)):
                continue
            if activation - other_activation < float(
                rule.get("minimumFamilyMargin", -1.0)
            ):
                continue
            hits.append(
                Hit(
                    GENERIC_INSTRUMENT[family],
                    max(0.0, onset + latency),
                    confidence,
                )
            )
    return sorted(hits, key=lambda hit: (hit.onset, hit.instrument))


def apply_route_post_filter(
    hits: list[dict[str, object]], route: str
) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    # Acoustic drum recordings commonly contain intentional kick + hi-hat
    # unisons.  The older slow-swing suppression was designed for separated
    # full-song stems and incorrectly deletes those genuine acoustic hits.
    if route == "adtof_acoustic_precision":
        return hits, ()
    return filter_rhythm_inconsistencies(hits)


def full_mix_fusion(
    direct: np.ndarray, stem: np.ndarray, rules: dict[str, Any]
) -> list[Hit]:
    frame_count = min(len(direct), len(stem))
    hits: list[Hit] = []
    for family in FAMILIES:
        class_index = ADTOF_CLASS_INDEX[family]
        rule = rules["peakRules"][family]
        stem_weight = float(rule["stemWeight"])
        activation = (
            stem_weight * stem[:frame_count, class_index]
            + (1 - stem_weight) * direct[:frame_count, class_index]
        )
        peak_rule = {
            "threshold": rule["threshold"],
            "preAverageSeconds": rule["preAverageSeconds"],
            "preMaximumSeconds": 0.02,
            "combineSeconds": 0.02,
        }
        hits.extend(
            Hit(GENERIC_INSTRUMENT[family], onset, confidence)
            for onset, confidence in process_activation(activation, peak_rule)
        )
    return sorted(hits, key=lambda hit: (hit.onset, hit.instrument))


def transcribe(
    *,
    stem: Path,
    mixture: Path | None,
    repository: Path,
    config_path: Path,
    device: str,
    drum_only_profile: str = "electronic",
) -> tuple[list[Hit], dict[str, Any]]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_config(config, repository)
    weights = resolve(repository, config["components"]["adtofWeights"]["path"])
    model = load_adtof_model(weights, device)
    stem_activations = adtof_activations(model, stem, device)
    if mixture is not None:
        direct_activations = adtof_activations(model, mixture, device)
        return full_mix_fusion(
            direct_activations, stem_activations, config["fullMix"]
        ), {
            "route": "direct+htdemucs_ft_stem",
            "directStemFusion": True,
            "tempoAwareRecovery": False,
        }

    if drum_only_profile == "acoustic":
        return acoustic_precision_hits(stem_activations, config["drumOnly"]), {
            "route": "adtof_acoustic_precision",
            "drumOnlyProfile": "acoustic",
            "directStemFusion": False,
            "tempoAwareRecovery": False,
        }

    ensemble_path = resolve(
        repository, config["components"]["stackedEnsemble"]["path"]
    )
    probabilities, frame_seconds, ensemble_config = load_ensemble_probabilities(
        stem, repository, ensemble_path, device
    )
    hits, counters = drum_only_fusion(
        stem_activations,
        probabilities,
        frame_seconds,
        ensemble_config,
        config["drumOnly"],
    )
    return hits, {
        "route": "first_party_ensemble+adtof",
        "drumOnlyProfile": "electronic",
        "directStemFusion": False,
        "tempoAwareRecovery": True,
        **counters,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="drum stem")
    parser.add_argument("--mixture-input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=REPOSITORY)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("ml/configs/drumscribe-recall-fusion-v2.json"),
    )
    parser.add_argument("--device", choices=("cpu", "cuda", "mps"), default="cpu")
    parser.add_argument(
        "--drum-only-profile",
        choices=("electronic", "acoustic"),
        default="electronic",
        help="Select the isolated-drum timbre profile; full mixtures ignore this option.",
    )
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    config_path = (
        args.config.resolve(strict=True)
        if args.config.is_absolute()
        else (repository / args.config).resolve(strict=True)
    )
    stem = args.input.resolve(strict=True)
    mixture = args.mixture_input.resolve(strict=True) if args.mixture_input else None
    hits, metadata = transcribe(
        stem=stem,
        mixture=mixture,
        repository=repository,
        config_path=config_path,
        device=args.device,
        drum_only_profile=args.drum_only_profile,
    )
    payload_hits = [
        {
            "instrument": hit.instrument,
            "onsetSeconds": round(hit.onset, 6),
            "velocity": 100,
            "confidence": round(hit.confidence, 7),
        }
        for hit in hits
    ]
    filtered, adjustments = apply_route_post_filter(
        payload_hits, str(metadata["route"])
    )
    write_hits_contract(
        args.output.resolve(),
        provider=PROVIDER,
        hits=filtered,
        metadata={
            "decoderVersion": PROVIDER,
            "configSha256": sha256(config_path),
            "adjustments": list(adjustments),
            "removedHitCount": len(payload_hits) - len(filtered),
            **metadata,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
