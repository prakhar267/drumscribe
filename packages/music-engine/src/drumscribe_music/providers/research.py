"""Local-development onset and spectral heuristics using optional librosa/numpy."""

from __future__ import annotations

import importlib
from pathlib import Path

from ..licensing import LicenseStatus, ProviderLicense
from ..models import Instrument, RawDrumHit
from ..tempo import TempoMap


class ResearchDependencyError(RuntimeError):
    pass


class ResearchDrumTranscriptionProvider:
    """Conservative kick/snare/closed-hat baseline, not a trained drum model."""

    provider_id = "research-spectral-v1"
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
        envelope = librosa.onset.onset_strength(
            y=signal, sr=sample_rate, hop_length=self.hop_length, aggregate=np.median
        )
        frames = librosa.onset.onset_detect(
            onset_envelope=envelope,
            sr=sample_rate,
            hop_length=self.hop_length,
            backtrack=True,
            units="frames",
        )
        if len(frames) == 0:
            return []
        peak = max(float(envelope.max()), 1e-9)
        hits: list[RawDrumHit] = []
        window = max(256, int(sample_rate * 0.08))
        for frame in frames:
            start = int(librosa.frames_to_samples(frame, hop_length=self.hop_length))
            clip = signal[start : start + window]
            if clip.size < 32:
                continue
            magnitude = np.abs(np.fft.rfft(clip * np.hanning(clip.size)))
            frequencies = np.fft.rfftfreq(clip.size, 1 / sample_rate)
            total = float(magnitude.sum()) + 1e-12
            low_ratio = float(magnitude[frequencies < 180].sum()) / total
            high_ratio = float(magnitude[frequencies > 5_000].sum()) / total
            instrument, margin = _classify_spectrum(low_ratio, high_ratio)
            strength = float(envelope[min(int(frame), len(envelope) - 1)]) / peak
            confidence = max(0.25, min(0.88, 0.35 + 0.35 * strength + 0.18 * margin))
            rms = float(np.sqrt(np.mean(clip * clip)))
            velocity = max(20, min(127, round(28 + 99 * min(1.0, rms * 8))))
            hits.append(
                RawDrumHit(
                    instrument,
                    onset_seconds=start / sample_rate,
                    velocity=velocity,
                    confidence=confidence,
                    metadata={
                        "provider": self.provider_id,
                        "lowRatio": round(low_ratio, 5),
                        "highRatio": round(high_ratio, 5),
                    },
                )
            )
        return hits


class ResearchBeatTrackingProvider:
    provider_id = "research-librosa-beat-v1"
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
        bpm = float(np.asarray(tempo).reshape(-1)[0]) if np.asarray(tempo).size else 120.0
        bpm = min(300.0, max(30.0, bpm))
        beat_count = int(len(beat_frames))
        confidence = min(
            0.85, max(0.25, beat_count / max(8.0, len(signal) / sample_rate * bpm / 60))
        )
        from ..tempo import TempoChange, TimeSignature

        return TempoMap(
            (TempoChange(0, bpm, confidence),),
            (TimeSignature(4, 4, confidence=min(confidence, 0.65)),),
        )


def _analysis_dependencies():
    try:
        librosa = importlib.import_module("librosa")
        np = importlib.import_module("numpy")
    except ImportError as exc:
        raise ResearchDependencyError(
            "research analysis requires `pip install drumscribe-music[audio]`"
        ) from exc
    return librosa, np


def _classify_spectrum(low_ratio: float, high_ratio: float) -> tuple[Instrument, float]:
    """Map intentionally broad spectral evidence into only three reliable classes."""

    if low_ratio >= 0.30:
        return Instrument.KICK, min(1.0, (low_ratio - 0.30) / 0.35)
    if high_ratio >= 0.23:
        return Instrument.CLOSED_HIHAT, min(1.0, (high_ratio - 0.23) / 0.35)
    return Instrument.SNARE, min(1.0, abs(0.30 - low_ratio) + abs(0.23 - high_ratio))
