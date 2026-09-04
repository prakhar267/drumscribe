"""Local-development onset and spectral heuristics using optional librosa/numpy."""

from __future__ import annotations

import importlib
import statistics
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from ..licensing import LicenseStatus, ProviderLicense
from ..models import Instrument, RawDrumHit
from ..tempo import TempoMap


class ResearchDependencyError(RuntimeError):
    pass


class ResearchDrumTranscriptionProvider:
    """Multi-band spectral-feature baseline, not a trained drum model."""

    provider_id = "research-spectral-v2"
    license = ProviderLicense(
        provider_id=provider_id,
        status=LicenseStatus.UNRESOLVED,
        code_license="project code; optional dependencies ISC/BSD",
        weights_license="no weights",
        training_data_license="no training data",
        attribution_required=True,
        distribution_restrictions="Dependency notices must be retained.",
        decision="Local research/benchmarking only until a production quality and legal review.",
    )

    def __init__(self, *, sample_rate: int = 22_050, hop_length: int = 256) -> None:
        self.sample_rate = sample_rate
        self.hop_length = hop_length

    def transcribe(self, audio_path: Path) -> list[RawDrumHit]:
        librosa, np = _analysis_dependencies()
        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        signal, sample_rate = librosa.load(path, sr=self.sample_rate, mono=True)
        if signal.size == 0:
            return []
        candidates = _candidate_onsets(
            librosa,
            np,
            signal,
            sample_rate,
            self.hop_length,
        )
        if not candidates:
            return []
        hits: list[RawDrumHit] = []
        window = max(256, int(sample_rate * 0.20))
        for frame, strength in candidates:
            start = int(librosa.frames_to_samples(frame, hop_length=self.hop_length))
            clip = signal[start : start + window]
            if clip.size < 32:
                continue
            features = _spectral_features(np, clip, sample_rate)
            instrument, margin = _classify_features(features)
            confidence = max(0.25, min(0.88, 0.35 + 0.35 * strength + 0.18 * margin))
            velocity_clip = clip[: max(32, int(sample_rate * 0.08))]
            rms = float(np.sqrt(np.mean(velocity_clip * velocity_clip)))
            velocity = max(20, min(127, round(28 + 99 * min(1.0, rms * 8))))
            hits.append(
                RawDrumHit(
                    instrument,
                    onset_seconds=start / sample_rate,
                    velocity=velocity,
                    confidence=confidence,
                    metadata={
                        "provider": self.provider_id,
                        **{name: round(float(value), 5) for name, value in features.items()},
                    },
                )
            )
        return hits


class ResearchBeatTrackingProvider:
    provider_id = "research-librosa-beat-v2"
    license = ProviderLicense(
        provider_id=provider_id,
        status=LicenseStatus.UNRESOLVED,
        code_license="project code; librosa ISC and dependencies",
        weights_license="no weights",
        training_data_license="no training data",
        attribution_required=True,
        decision="Local research only pending production dependency and quality review.",
    )

    def track(self, audio_path: Path) -> TempoMap:
        librosa, np = _analysis_dependencies()
        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        signal, sample_rate = librosa.load(path, sr=22_050, mono=True)
        if signal.size == 0:
            return TempoMap.constant(120)
        onset = librosa.onset.onset_strength(y=signal, sr=sample_rate)
        tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset, sr=sample_rate)
        fallback_bpm = float(np.asarray(tempo).reshape(-1)[0]) if np.asarray(tempo).size else 120.0
        fallback_bpm = min(300.0, max(30.0, fallback_bpm))
        beat_count = int(len(beat_frames))
        confidence = min(
            0.85,
            max(0.25, beat_count / max(8.0, len(signal) / sample_rate * fallback_bpm / 60)),
        )
        from ..tempo import TempoChange, TimeSignature

        if beat_count == 0:
            return TempoMap.constant(fallback_bpm)

        beat_times = np.asarray(librosa.frames_to_time(beat_frames, sr=sample_rate), dtype=float)
        if beat_count == 1:
            return TempoMap(
                (TempoChange(0, fallback_bpm, confidence),),
                (TimeSignature(4, 4, confidence=min(confidence, 0.65)),),
                offset_seconds=float(beat_times[0]),
            )

        # Preserve the tracker's actual beat anchors. A single global tempo accumulates
        # visible notation drift on human performances even when every detected hit is
        # correctly timed. One piecewise segment per beat keeps beat_to_seconds(i)
        # aligned with the observed beat timestamp while still interpolating sub-beats.
        intervals = np.diff(beat_times)
        local_bpms = np.clip(60.0 / intervals, 30.0, 300.0)
        changes = tuple(
            TempoChange(index, float(local_bpms[min(index, len(local_bpms) - 1)]), confidence)
            for index in range(beat_count)
        )
        return TempoMap(
            changes,
            (TimeSignature(4, 4, confidence=min(confidence, 0.65)),),
            offset_seconds=float(beat_times[0]),
        )


class ResearchBeatThisTrackingProvider:
    """Neural beat/downbeat tracker under DrumScribe's separate commercial grant."""

    provider_id = "research-beat-this-v1"
    license = ProviderLicense(
        provider_id=provider_id,
        status=LicenseStatus.COMMERCIAL_ALLOWED,
        code_license="Beat This code and published weights: MIT",
        weights_license="MIT plus DrumScribe commercial-rights attestation",
        training_data_license=(
            "commercial model-use rights covered by OWNER-ATTESTATION-2026-09-05"
        ),
        attribution_required=True,
        distribution_restrictions=(
            "Retain MIT attribution and keep the separate commercial grant in the company audit."
        ),
        decision=(
            "Self-hosted commercial inference approved by the company owner under "
            "OWNER-ATTESTATION-2026-09-05."
        ),
    )

    def __init__(self, *, checkpoint: str = "final0", device: str | None = None) -> None:
        if not checkpoint or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in checkpoint
        ):
            raise ValueError("invalid Beat This checkpoint name")
        self.checkpoint = checkpoint
        self.device = device or _best_torch_device()
        self.version = f"beat-this/{checkpoint}"
        if checkpoint != "final0":
            self.license = replace(
                type(self).license,
                status=LicenseStatus.UNRESOLVED,
                decision=(
                    f"Checkpoint {checkpoint!r} is outside OWNER-ATTESTATION-2026-09-05; "
                    "production use requires a separate approval."
                ),
            )

    def track(self, audio_path: Path) -> TempoMap:
        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        model = _beat_this_model(self.checkpoint, self.device)
        beats, downbeats = model(path)
        beat_times = sorted({float(value) for value in beats if float(value) >= 0})
        downbeat_times = sorted({float(value) for value in downbeats if float(value) >= 0})
        if len(beat_times) < 2:
            return ResearchBeatTrackingProvider().track(path)
        return _tempo_map_from_observed_beats(beat_times, downbeat_times)


def _tempo_map_from_observed_beats(
    beat_times: list[float], downbeat_times: list[float]
) -> TempoMap:
    """Preserve neural beat anchors while aligning beat zero to an inferred bar boundary."""

    from ..tempo import TempoChange, TimeSignature

    intervals = [second - first for first, second in zip(beat_times, beat_times[1:], strict=False)]
    positive_intervals = [value for value in intervals if value > 0]
    if not positive_intervals:
        return TempoMap.constant(120)
    median_interval = statistics.median(positive_intervals)
    downbeat_indices = [
        min(range(len(beat_times)), key=lambda index: abs(beat_times[index] - downbeat))
        for downbeat in downbeat_times
        if min(abs(beat - downbeat) for beat in beat_times) <= 0.08
    ]
    meter_differences = [
        second - first
        for first, second in zip(downbeat_indices, downbeat_indices[1:], strict=False)
        if second > first
    ]
    numerator = round(statistics.median(meter_differences)) if meter_differences else 4
    if not 2 <= numerator <= 12:
        numerator = 4

    first_downbeat_index = downbeat_indices[0] if downbeat_indices else 0
    virtual_beats = (numerator - first_downbeat_index % numerator) % numerator
    offset_seconds = beat_times[0] - virtual_beats * median_interval
    if offset_seconds < 0:
        virtual_beats = 0
        offset_seconds = beat_times[0]

    confidence = 0.95 if len(downbeat_indices) >= 2 else 0.85
    local_bpms = [min(300.0, max(30.0, 60.0 / value)) for value in positive_intervals]
    changes_by_beat: dict[int, TempoChange] = {0: TempoChange(0, local_bpms[0], confidence)}
    for index, bpm in enumerate(local_bpms):
        changes_by_beat[virtual_beats + index] = TempoChange(virtual_beats + index, bpm, confidence)
    last_beat = virtual_beats + len(beat_times) - 1
    changes_by_beat[last_beat] = TempoChange(last_beat, local_bpms[-1], confidence)
    return TempoMap(
        tuple(changes_by_beat.values()),
        (TimeSignature(numerator, 4, confidence=confidence),),
        offset_seconds=offset_seconds,
    )


def _best_torch_device() -> str:
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return "cpu"
    if bool(torch.cuda.is_available()):
        return "cuda"
    if bool(getattr(torch.backends, "mps", None)) and bool(torch.backends.mps.is_available()):
        return "mps"
    return "cpu"


@lru_cache(maxsize=4)
def _beat_this_model(checkpoint: str, device: str):
    try:
        inference = importlib.import_module("beat_this.inference")
    except ImportError as exc:
        raise ResearchDependencyError(
            "accurate beat tracking requires `pip install drumscribe-music[accurate-beats]`"
        ) from exc
    return inference.File2Beats(checkpoint_path=checkpoint, device=device, dbn=False)


def _analysis_dependencies():
    try:
        librosa = importlib.import_module("librosa")
        np = importlib.import_module("numpy")
    except ImportError as exc:
        raise ResearchDependencyError(
            "research analysis requires `pip install drumscribe-music[audio]`"
        ) from exc
    return librosa, np


def _candidate_onsets(librosa, np, signal, sample_rate: int, hop_length: int):
    """Find high-confidence broadband attacks before multi-class analysis."""

    envelope = librosa.onset.onset_strength(
        y=signal,
        sr=sample_rate,
        hop_length=hop_length,
        aggregate=np.median,
    )
    peak = max(float(envelope.max()), 1e-9)
    frames = librosa.onset.onset_detect(
        onset_envelope=envelope,
        sr=sample_rate,
        hop_length=hop_length,
        backtrack=True,
        units="frames",
    )
    return [
        (int(frame), float(envelope[min(int(frame), len(envelope) - 1)]) / peak) for frame in frames
    ]


def _spectral_features(np, clip, sample_rate: int) -> dict[str, float]:
    fft_size = min(int(clip.size), 2_048)
    attack = clip[:fft_size]
    magnitude = np.abs(np.fft.rfft(attack * np.hanning(fft_size)))
    frequencies = np.fft.rfftfreq(fft_size, 1 / sample_rate)
    total = float(magnitude.sum()) + 1e-12

    def ratio(minimum: float, maximum: float) -> float:
        mask = (frequencies >= minimum) & (frequencies < maximum)
        return float(magnitude[mask].sum()) / total

    low = ratio(0, 180)
    low_mid = ratio(180, 700)
    mid = ratio(700, 2_000)
    high_mid = ratio(2_000, 5_000)
    high = ratio(5_000, 12_000)
    centroid = float((magnitude * frequencies).sum()) / total / sample_rate
    flatness = float(np.exp(np.mean(np.log(magnitude + 1e-8))) / (np.mean(magnitude) + 1e-8))

    def segment_rms(start_seconds: float, end_seconds: float) -> float:
        segment = clip[int(start_seconds * sample_rate) : int(end_seconds * sample_rate)]
        if segment.size == 0:
            return 1e-9
        return float(np.sqrt(np.mean(segment * segment))) + 1e-9

    decay = float(np.log10(segment_rms(0.08, 0.18) / segment_rms(0, 0.03)))
    zero_cross_clip = clip[: max(2, int(0.08 * sample_rate))]
    zero_crossing_rate = float(np.mean(zero_cross_clip[1:] * zero_cross_clip[:-1] < 0))
    body_mask = (frequencies >= 60) & (frequencies < 500)
    body_magnitude = magnitude[body_mask]
    body_frequencies = frequencies[body_mask]
    dominant_body_hz = (
        float(body_frequencies[int(np.argmax(body_magnitude))]) if body_magnitude.size else 0.0
    )
    return {
        "lowRatio": low,
        "lowMidRatio": low_mid,
        "midRatio": mid,
        "highMidRatio": high_mid,
        "highRatio": high,
        "centroid": centroid,
        "flatness": flatness,
        "decay": decay,
        "zeroCrossingRate": zero_crossing_rate,
        "dominantBodyHz": dominant_body_hz,
    }


def _classify_features(features: dict[str, float]) -> tuple[Instrument, float]:
    """Classify using physical spectral/decay evidence across the supported kit."""

    low = features["lowRatio"]
    low_mid = features["lowMidRatio"]
    mid = features["midRatio"]
    high_mid = features["highMidRatio"]
    high = features["highRatio"]
    centroid = features["centroid"]
    flatness = features["flatness"]
    decay = features["decay"]
    zero_crossing_rate = features["zeroCrossingRate"]
    body = low_mid + mid
    brightness = high / max(body, 1e-9)

    if low >= 0.16 and low > body * 0.75:
        return Instrument.KICK, min(1.0, (low - 0.16) * 4)
    if centroid < 0.125 and low >= 0.085 and body >= 0.22 and high < 0.24:
        dominant = features["dominantBodyHz"]
        instrument = (
            Instrument.FLOOR_TOM
            if dominant < 110
            else Instrument.LOW_TOM
            if dominant < 160
            else Instrument.MID_TOM
            if dominant < 230
            else Instrument.HIGH_TOM
        )
        return instrument, min(1.0, body)
    if decay < -0.95 and low < 0.10 and flatness < 0.53 and 0.10 < centroid < 0.29:
        instrument = (
            Instrument.TAMBOURINE
            if high >= 0.32 or zero_crossing_rate >= 0.22
            else Instrument.CROSS_STICK
        )
        return instrument, min(1.0, abs(decay + 0.95))
    if body >= 0.23 and brightness < 1.45:
        return Instrument.SNARE, min(1.0, body)
    if decay > -0.28 and high_mid >= 0.25 and high < 0.53:
        return Instrument.CRASH, min(1.0, decay + 0.28 + high_mid)
    if brightness >= 1.20 or high >= 0.36 or zero_crossing_rate >= 0.13:
        return Instrument.CLOSED_HIHAT, min(1.0, max(brightness - 1.20, high - 0.36))
    return Instrument.SNARE, min(1.0, body)


def _classify_spectrum(low_ratio: float, high_ratio: float) -> tuple[Instrument, float]:
    """Map intentionally broad spectral evidence into only three reliable classes."""

    if low_ratio >= 0.30:
        return Instrument.KICK, min(1.0, (low_ratio - 0.30) / 0.35)
    if high_ratio >= 0.23:
        return Instrument.CLOSED_HIHAT, min(1.0, (high_ratio - 0.23) / 0.35)
    return Instrument.SNARE, min(1.0, abs(0.30 - low_ratio) + abs(0.23 - high_ratio))
