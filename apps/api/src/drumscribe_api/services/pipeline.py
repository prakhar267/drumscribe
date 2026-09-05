import asyncio
import importlib
import inspect
import json
import math
import shlex
import shutil
import socket
import statistics
import tempfile
import time
import uuid
from collections.abc import Iterable
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import structlog
from botocore.exceptions import (  # type: ignore[import-untyped]
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..database import Database
from ..enums import (
    TERMINAL_JOB_STAGES,
    AssetKind,
    AssetStatus,
    Environment,
    EventSource,
    ExportFormat,
    Instrument,
    JobErrorCode,
    JobStage,
    ProjectStatus,
    RevisionKind,
    UserKind,
)
from ..errors import APIError
from ..models import (
    AudioAsset,
    DrumEvent,
    ModelRun,
    ProcessingJob,
    Project,
    Transcription,
    TranscriptionRevision,
    User,
)
from ..security import utcnow
from .audio import AudioProbe
from .commercial_providers import (
    AudioShakeSourceSeparationProvider,
    CommercialHTTPConfig,
    CommercialProviderError,
    KlangioBeatTrackingProvider,
    KlangioDrumTranscriptionProvider,
    MusicAISourceSeparationProvider,
)
from .exports import generate_export_bytes
from .jobs import STAGE_ORDER, transition_job
from .pipeline_contracts import (
    BeatTrackingResult,
    DrumTranscriptionResult,
    ProviderCategory,
    ProviderRunMetadata,
    RawDrumHit,
    SeparatedAudioResult,
)
from .revisions import create_revision
from .storage import ObjectNotFoundError, PrivateStorage

logger = structlog.get_logger(__name__)

TRANSIENT_PIPELINE_ERRORS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    ConnectTimeoutError,
    ConnectionClosedError,
    EndpointConnectionError,
    ReadTimeoutError,
    OperationalError,
)


RAW_INSTRUMENT_MAP: dict[str, Instrument] = {
    "kick": Instrument.KICK,
    "bass_drum": Instrument.KICK,
    "bd": Instrument.KICK,
    "snare": Instrument.SNARE,
    "sd": Instrument.SNARE,
    "cross_stick": Instrument.CROSS_STICK,
    "closed_hihat": Instrument.CLOSED_HIHAT,
    "closed_hi_hat": Instrument.CLOSED_HIHAT,
    "hihat": Instrument.CLOSED_HIHAT,
    "hh": Instrument.CLOSED_HIHAT,
    "open_hihat": Instrument.OPEN_HIHAT,
    "open_hi_hat": Instrument.OPEN_HIHAT,
    "pedal_hihat": Instrument.PEDAL_HIHAT,
    "ride": Instrument.RIDE,
    "ride_bell": Instrument.RIDE_BELL,
    "crash": Instrument.CRASH,
    "high_tom": Instrument.HIGH_TOM,
    "mid_tom": Instrument.MID_TOM,
    "low_tom": Instrument.LOW_TOM,
    "floor_tom": Instrument.FLOOR_TOM,
    "tambourine": Instrument.TAMBOURINE,
    "tmb": Instrument.TAMBOURINE,
}


def canonical_instrument(value: object) -> Instrument:
    if isinstance(value, Instrument):
        return value
    raw = getattr(value, "value", value)
    normalized = str(raw).strip().casefold().replace("-", "_").replace(" ", "_")
    try:
        return Instrument(normalized.upper())
    except ValueError:
        mapped = RAW_INSTRUMENT_MAP.get(normalized)
        if mapped is None:
            raise ValueError(f"Unsupported drum instrument class: {raw!r}") from None
        return mapped


class MusicEngineAdapter:
    """Narrow boundary around the independently versioned `drumscribe_music` package."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate_configuration(self) -> None:
        if self.settings.pipeline_provider == "development":
            return
        engine = self._engine()
        for provider in (
            self._transcription_provider(engine),
            self._separation_provider(engine),
            self._beat_provider(engine),
        ):
            category = getattr(provider, "category", None)
            if category is ProviderCategory.PRODUCTION_COMMERCIAL:
                if not self.settings.commercial_provider_license_confirmed:
                    raise RuntimeError(
                        "commercial providers require explicit license and contract approval"
                    )
                continue
            engine.require_production_safe(
                provider, production=self.settings.environment == Environment.PRODUCTION
            )

    @staticmethod
    def _engine() -> Any:
        try:
            return importlib.import_module("drumscribe_music")
        except ImportError as exc:
            raise RuntimeError("The configured music engine is unavailable.") from exc

    @staticmethod
    def _provider(engine: Any, provider_name: str, aliases: dict[str, str]) -> Any:
        normalized = provider_name.casefold()
        class_name = aliases.get(normalized, provider_name)
        provider_class = getattr(engine, class_name, None)
        if provider_class is None:
            raise RuntimeError(f"Configured provider {provider_name!r} is not installed.")
        try:
            return provider_class()
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Configured provider {provider_name!r} is not ready.") from exc

    def _transcription_provider(self, engine: Any) -> Any:
        selected = self.settings.music_transcription_provider.casefold()
        if selected == "klangio_drums":
            return KlangioDrumTranscriptionProvider(self._klangio_config())
        external = {
            "yourmt3_plus": (
                "YourMT3PlusTranscriptionProvider",
                self.settings.yourmt3_command,
                self.settings.yourmt3_model_version,
            ),
            "oaf_drums": (
                "OaFDrumsTranscriptionProvider",
                self.settings.oaf_drums_command,
                self.settings.oaf_drums_model_version,
            ),
            "adtof": (
                "ADTOFResearchTranscriptionProvider",
                self.settings.adtof_command,
                self.settings.adtof_model_version,
            ),
            "drumscribe_hybrid": (
                "DrumScribeHybridTranscriptionProvider",
                self.settings.hybrid_command,
                self.settings.hybrid_model_version,
            ),
            "drumscribe_recall_fusion": (
                "DrumScribeRecallFusionTranscriptionProvider",
                self.settings.recall_fusion_command,
                self.settings.recall_fusion_model_version,
            ),
        }
        if selected in external:
            class_name, command, version = external[selected]
            if not command:
                raise RuntimeError(
                    f"Configured provider {selected!r} requires its model command setting."
                )
            try:
                argv = shlex.split(command)
            except ValueError as exc:
                raise RuntimeError(f"Configured provider {selected!r} has invalid argv.") from exc
            provider_class = getattr(engine, class_name, None)
            if provider_class is None:
                raise RuntimeError(f"Configured provider {selected!r} is not installed.")
            return provider_class(
                argv,
                model_version=version,
                timeout_seconds=self.settings.provider_timeout_seconds,
            )
        aliases = {
            "mock": "MockDrumTranscriptionProvider",
            "research": "ResearchDrumTranscriptionProvider",
        }
        return self._provider(engine, self.settings.music_transcription_provider, aliases)

    def transcription_input_kind(self) -> str:
        """Return whether the selected detector expects a full mix or drum stem."""

        if self.settings.pipeline_provider == "development":
            return "drum_stem"
        provider = self._transcription_provider(self._engine())
        input_kind = str(getattr(provider, "input_kind", "drum_stem"))
        if input_kind not in {"full_mix", "drum_stem"}:
            raise RuntimeError("Configured transcription provider has an invalid input kind.")
        return input_kind

    def _separation_provider(self, engine: Any) -> Any:
        selected = self.settings.source_separation_provider.casefold()
        if selected == "audioshake":
            return AudioShakeSourceSeparationProvider(
                self._commercial_config(
                    api_key=self.settings.audioshake_api_key,
                    contract_reference=self.settings.audioshake_contract_reference,
                    base_url=self.settings.audioshake_api_url,
                ),
                model=self.settings.audioshake_separation_model,
            )
        if selected == "music_ai":
            return MusicAISourceSeparationProvider(
                self._commercial_config(
                    api_key=self.settings.music_ai_api_key,
                    contract_reference=self.settings.music_ai_contract_reference,
                    base_url=self.settings.music_ai_api_url,
                ),
                workflow=self.settings.music_ai_separation_workflow or "",
                result_key=self.settings.music_ai_drum_result_key,
            )
        class_name = {
            "passthrough": "PassthroughSourceSeparationProvider",
            "demucs": "DemucsAdapter",
        }
        return self._provider(engine, self.settings.source_separation_provider, class_name)

    def _beat_provider(self, engine: Any) -> Any:
        if self.settings.beat_tracking_provider.casefold() == "klangio":
            return KlangioBeatTrackingProvider(self._klangio_config())
        class_name = {
            "mock": "MockBeatTrackingProvider",
            "research": "ResearchBeatThisTrackingProvider",
            "research_accurate": "ResearchBeatThisTrackingProvider",
            "research_librosa": "ResearchBeatTrackingProvider",
        }
        return self._provider(engine, self.settings.beat_tracking_provider, class_name)

    def _klangio_config(self) -> CommercialHTTPConfig:
        return self._commercial_config(
            api_key=self.settings.klangio_api_key,
            contract_reference=self.settings.klangio_contract_reference,
            base_url=self.settings.klangio_api_url,
        )

    def _commercial_config(
        self,
        *,
        api_key: Any,
        contract_reference: str | None,
        base_url: str,
    ) -> CommercialHTTPConfig:
        return CommercialHTTPConfig(
            api_key=api_key.get_secret_value() if api_key else "",
            contract_reference=contract_reference or "",
            base_url=base_url,
            timeout_seconds=self.settings.provider_timeout_seconds,
            poll_interval_seconds=self.settings.provider_poll_interval_seconds,
        )

    async def separate(self, source: Path, destination: Path) -> ProviderRunMetadata:
        if self.settings.pipeline_provider == "development":
            started = time.monotonic()
            await asyncio.to_thread(shutil.copyfile, source, destination)
            return ProviderRunMetadata(
                provider="passthrough-development",
                category=ProviderCategory.TEST_FIXTURE,
                model_version="1",
                request_id=None,
                processing_ms=round((time.monotonic() - started) * 1000),
                raw_metadata={"audioDerived": False, "operation": "byte-for-byte copy"},
            )
        engine = self._engine()
        provider = self._separation_provider(engine)
        if getattr(provider, "category", None) is ProviderCategory.PRODUCTION_COMMERCIAL:
            result = await provider.separate_drums(source, destination)
            return cast(SeparatedAudioResult, result).metadata
        engine.require_production_safe(
            provider,
            production=self.settings.environment == Environment.PRODUCTION,
        )
        started = time.monotonic()
        result = provider.separate_drums(source, destination)
        if inspect.isawaitable(result):
            await result
        return ProviderRunMetadata(
            provider=str(getattr(provider, "provider_id", provider.__class__.__name__)),
            category=(
                ProviderCategory.PRODUCTION_COMMERCIAL
                if self.settings.environment == Environment.PRODUCTION
                else ProviderCategory.DEVELOPMENT_RESEARCH
            ),
            model_version=str(getattr(provider, "version", "unknown")),
            request_id=None,
            processing_ms=round((time.monotonic() - started) * 1000),
            contract_reference=(
                self.settings.commercial_provider_approval_reference
                if self.settings.environment == Environment.PRODUCTION
                else None
            ),
        )

    async def track_beats(self, audio_path: Path) -> dict[str, Any]:
        engine = self._engine()
        provider = (
            engine.MockBeatTrackingProvider()
            if self.settings.pipeline_provider == "development"
            else self._beat_provider(engine)
        )
        if getattr(provider, "category", None) is ProviderCategory.PRODUCTION_COMMERCIAL:
            tracked = await provider.track(audio_path)
            return self._commercial_beat_payload(tracked)
        engine.require_production_safe(
            provider, production=self.settings.environment == Environment.PRODUCTION
        )
        started = time.monotonic()
        result = provider.track(audio_path)
        if inspect.isawaitable(result):
            result = await result
        first_tempo = result.changes[0]
        first_signature = result.time_signatures[0]
        display_bpm = statistics.median(change.bpm for change in result.changes)
        provider_id = str(getattr(provider, "provider_id", provider.__class__.__name__))
        metadata = ProviderRunMetadata(
            provider=provider_id,
            category=(
                ProviderCategory.TEST_FIXTURE
                if self.settings.pipeline_provider == "development"
                else ProviderCategory.PRODUCTION_COMMERCIAL
                if self.settings.environment == Environment.PRODUCTION
                else ProviderCategory.DEVELOPMENT_RESEARCH
            ),
            model_version=str(getattr(provider, "version", "unknown")),
            request_id=None,
            processing_ms=round((time.monotonic() - started) * 1000),
            confidence=min(float(first_tempo.confidence), float(first_signature.confidence)),
            raw_metadata={"audioDerived": self.settings.pipeline_provider != "development"},
            contract_reference=(
                self.settings.commercial_provider_approval_reference
                if self.settings.environment == Environment.PRODUCTION
                else None
            ),
        )
        return {
            "tempoBpm": float(display_bpm),
            "timeSignatureNumerator": int(first_signature.numerator),
            "timeSignatureDenominator": int(first_signature.denominator),
            "confidence": min(float(first_tempo.confidence), float(first_signature.confidence)),
            "tempoMap": [
                {
                    "kind": "tempo",
                    "startBeat": str(change.start_beat),
                    "bpm": float(change.bpm),
                    "confidence": float(change.confidence),
                }
                for change in result.changes
            ],
            "timeSignatures": [
                {
                    "kind": "timeSignature",
                    "startBeat": str(signature.start_beat),
                    "numerator": signature.numerator,
                    "denominator": signature.denominator,
                    "confidence": float(signature.confidence),
                }
                for signature in result.time_signatures
            ],
            "offsetSeconds": float(result.offset_seconds),
            "beats": [
                {
                    "timeSeconds": float(result.beat_to_seconds(change.start_beat)),
                    "beatInMeasure": int(change.start_beat) % first_signature.numerator,
                    "measureIndex": int(change.start_beat) // first_signature.numerator,
                    "isDownbeat": int(change.start_beat) % first_signature.numerator == 0,
                    "confidence": float(change.confidence),
                }
                for change in result.changes
                if len(result.changes) > 1 and change.start_beat.denominator == 1
            ],
            "provider": provider_id,
            "providerMetadata": metadata.as_dict(),
        }

    @staticmethod
    def _commercial_beat_payload(result: BeatTrackingResult) -> dict[str, Any]:
        first = result.segments[0]
        return {
            "tempoBpm": first.bpm,
            "timeSignatureNumerator": first.time_signature_numerator,
            "timeSignatureDenominator": first.time_signature_denominator,
            "confidence": result.metadata.confidence,
            "tempoMap": [
                {
                    "kind": "tempo",
                    "startSeconds": segment.start_seconds,
                    "bpm": segment.bpm,
                    "startMeasure": segment.start_measure,
                    "confidence": result.metadata.confidence,
                }
                for segment in result.segments
            ],
            "timeSignatures": [
                {
                    "kind": "timeSignature",
                    "startSeconds": segment.start_seconds,
                    "startMeasure": segment.start_measure,
                    "numerator": segment.time_signature_numerator,
                    "denominator": segment.time_signature_denominator,
                    "confidence": result.metadata.confidence,
                }
                for segment in result.segments
            ],
            "offsetSeconds": result.bar_one_seconds,
            "beats": [
                {
                    "timeSeconds": beat.time_seconds,
                    "beatInMeasure": beat.beat_in_measure,
                    "measureIndex": beat.measure_index,
                    "isDownbeat": beat.is_downbeat,
                    "confidence": beat.confidence,
                }
                for beat in result.beats
            ],
            "provider": result.metadata.provider,
            "providerMetadata": result.metadata.as_dict(),
        }

    async def transcribe(
        self,
        audio_path: Path,
        duration: float,
        *,
        mixture_path: Path | None = None,
    ) -> DrumTranscriptionResult:
        if self.settings.pipeline_provider == "development":
            return DrumTranscriptionResult(
                hits=tuple(development_hits(duration)),
                metadata=ProviderRunMetadata(
                    provider="deterministic-development",
                    category=ProviderCategory.TEST_FIXTURE,
                    model_version="1",
                    request_id=None,
                    processing_ms=0,
                    raw_metadata={"audioDerived": False, "durationDerived": True},
                ),
            )
        try:
            engine = self._engine()
            provider = self._transcription_provider(engine)
            if getattr(provider, "category", None) is ProviderCategory.PRODUCTION_COMMERCIAL:
                return cast(DrumTranscriptionResult, await provider.transcribe(audio_path))
            engine.require_production_safe(
                provider, production=self.settings.environment == Environment.PRODUCTION
            )
        except RuntimeError as exc:
            raise APIError(
                500,
                JobErrorCode.INTERNAL_ERROR.value,
                "The configured music engine is unavailable.",
            ) from exc
        started = time.monotonic()
        if mixture_path is not None and hasattr(provider, "transcribe_multiview"):
            result = provider.transcribe_multiview(mixture_path, audio_path)
            used_multiview = True
        else:
            result = provider.transcribe(audio_path)
            used_multiview = False
        if inspect.isawaitable(result):
            result = await result
        hits: list[RawDrumHit] = []
        for item in result:
            instrument = getattr(item, "instrument", getattr(item, "instrument_class", "hihat"))
            hits.append(
                RawDrumHit(
                    instrument=canonical_instrument(instrument),
                    onset_seconds=float(getattr(item, "onset_seconds", getattr(item, "onset", 0))),
                    velocity=max(1, min(127, int(getattr(item, "velocity", 100)))),
                    confidence=max(0, min(1, float(getattr(item, "confidence", 0.5)))),
                )
            )
        version = str(getattr(provider, "version", getattr(engine, "__version__", "unknown")))
        return DrumTranscriptionResult(
            hits=tuple(hits),
            metadata=ProviderRunMetadata(
                provider=str(getattr(provider, "provider_id", provider.__class__.__name__)),
                category=(
                    ProviderCategory.PRODUCTION_COMMERCIAL
                    if self.settings.environment == Environment.PRODUCTION
                    else ProviderCategory.DEVELOPMENT_RESEARCH
                ),
                model_version=version,
                request_id=None,
                processing_ms=round((time.monotonic() - started) * 1000),
                raw_metadata={
                    "inputKind": str(getattr(provider, "input_kind", "drum_stem")),
                    "directStemFusion": used_multiview,
                },
                contract_reference=(
                    self.settings.commercial_provider_approval_reference
                    if self.settings.environment == Environment.PRODUCTION
                    else None
                ),
            ),
        )


def development_hits(duration: float) -> list[RawDrumHit]:
    """A deterministic, musically useful 120 BPM rock draft for local product work."""
    hits: list[RawDrumHit] = []
    eighth = 0.25
    steps = max(1, math.ceil(duration / eighth))
    for index in range(steps):
        onset = index * eighth
        if onset >= duration:
            break
        hits.append(
            RawDrumHit(
                Instrument.CLOSED_HIHAT,
                onset,
                82 if index % 2 else 94,
                0.91 if index % 8 < 6 else 0.72,
            )
        )
        beat = index % 8
        if beat in {0, 4}:
            hits.append(RawDrumHit(Instrument.KICK, onset, 112, 0.96))
        if beat in {2, 6}:
            hits.append(RawDrumHit(Instrument.SNARE, onset, 116, 0.95))
        if index % 32 == 0:
            hits.append(RawDrumHit(Instrument.CRASH, onset, 108, 0.86))
    return hits


def _quantize_hits_with_tempo(
    hits: Iterable[RawDrumHit],
    bpm: float = 120.0,
    numerator: int = 4,
    denominator: int = 4,
    *,
    timing_analysis: dict[str, Any] | None = None,
    rhythm_completion: bool = False,
) -> tuple[list[dict[str, Any]], Any, bool]:
    """Quantize and retain the exact tempo map used for the resulting notation."""

    engine = importlib.import_module("drumscribe_music")
    analysis = timing_analysis or {
        "tempoBpm": bpm,
        "timeSignatureNumerator": numerator,
        "timeSignatureDenominator": denominator,
    }
    tempo_map = _tempo_map_from_analysis(analysis, engine)
    engine_hits = [
        engine.RawDrumHit(
            instrument_class=hit.instrument.value,
            onset_seconds=hit.onset_seconds,
            velocity=hit.velocity,
            confidence=hit.confidence,
            duration_seconds=0.08,
        )
        for hit in hits
    ]
    completion_applied = False
    if rhythm_completion:
        completion = engine.complete_rhythm(engine_hits, tempo_map)
        engine_hits = list(completion.hits)
        tempo_map = completion.tempo_map
        completion_applied = completion.applied
    subdivision_names = {
        engine.GridSubdivision.QUARTER: "1/4",
        engine.GridSubdivision.EIGHTH: "1/8",
        engine.GridSubdivision.SIXTEENTH: "1/16",
        engine.GridSubdivision.THIRTY_SECOND: "1/32",
        engine.GridSubdivision.EIGHTH_TRIPLET: "1/8T",
        engine.GridSubdivision.SIXTEENTH_TRIPLET: "1/16T",
    }
    output: list[dict[str, Any]] = []
    # Automatic drafts favor readable quarter/eighth/sixteenth grids plus eighth
    # triplets. Thirty-second choices are still available in the editor, but allowing
    # them during first-pass inference turns normal human timing offsets into spurious
    # complex notation.
    quantization_settings = engine.QuantizationSettings(
        subdivisions=(
            engine.GridSubdivision.QUARTER,
            engine.GridSubdivision.EIGHTH,
            engine.GridSubdivision.SIXTEENTH,
            engine.GridSubdivision.EIGHTH_TRIPLET,
        )
    )
    for event in engine.quantize_hits(engine_hits, tempo_map, settings=quantization_settings):
        output.append(
            {
                "instrument": canonical_instrument(event.instrument),
                "onset_seconds": event.onset_seconds,
                "duration_seconds": max(0.001, event.duration_seconds),
                "velocity": event.velocity,
                "confidence": event.confidence,
                "source": EventSource.AI,
                "beat_position": float(event.beat_in_measure or 0),
                "measure_index": int(event.measure_index or 0),
                "subdivision": subdivision_names.get(event.subdivision, "free"),
                "quantized_onset": float(
                    event.quantized_onset_seconds
                    if event.quantized_onset_seconds is not None
                    else event.onset_seconds
                ),
                "manually_edited": False,
            }
        )
    return output, tempo_map, completion_applied


def quantize_hits(
    hits: Iterable[RawDrumHit],
    bpm: float = 120.0,
    numerator: int = 4,
    denominator: int = 4,
    *,
    timing_analysis: dict[str, Any] | None = None,
    rhythm_completion: bool = False,
) -> list[dict[str, Any]]:
    """Quantize without flattening an observed beat grid to one global BPM."""

    quantized, _, _ = _quantize_hits_with_tempo(
        hits,
        bpm,
        numerator,
        denominator,
        timing_analysis=timing_analysis,
        rhythm_completion=rhythm_completion,
    )
    return quantized


def _serialize_engine_tempo_map(tempo_map: Any) -> list[dict[str, Any]]:
    return [
        *[
            {
                "kind": "tempo",
                "startBeat": str(change.start_beat),
                "bpm": float(change.bpm),
                "confidence": float(change.confidence),
            }
            for change in tempo_map.changes
        ],
        *[
            {
                "kind": "timeSignature",
                "startBeat": str(signature.start_beat),
                "numerator": int(signature.numerator),
                "denominator": int(signature.denominator),
                "confidence": float(signature.confidence),
            }
            for signature in tempo_map.time_signatures
        ],
        {"kind": "offset", "offsetSeconds": float(tempo_map.offset_seconds)},
    ]


def _tempo_map_from_analysis(analysis: dict[str, Any], engine: Any) -> Any:
    """Rehydrate provider timing data into the music engine's exact tempo map."""

    confidence = float(analysis.get("confidence", 1.0) or 1.0)
    offset_seconds = max(0.0, float(analysis.get("offsetSeconds", 0.0) or 0.0))
    changes = [
        engine.TempoChange(
            item["startBeat"],
            float(item["bpm"]),
            float(item.get("confidence", confidence) or confidence),
        )
        for item in analysis.get("tempoMap", [])
        if isinstance(item, dict) and "startBeat" in item and "bpm" in item
    ]

    # Commercial trackers may provide timestamped beats instead of beat-indexed
    # tempo changes. Convert adjacent timestamps to exact piecewise beat segments.
    beats = sorted(
        (
            float(item["timeSeconds"]),
            float(item.get("confidence", confidence) or confidence),
        )
        for item in analysis.get("beats", [])
        if isinstance(item, dict) and "timeSeconds" in item
    )
    if not changes and len(beats) >= 2:
        offset_seconds = max(0.0, beats[0][0])
        for index, ((start, beat_confidence), (end, _)) in enumerate(pairwise(beats)):
            interval = end - start
            if interval <= 0:
                continue
            changes.append(
                engine.TempoChange(
                    index,
                    min(300.0, max(30.0, 60.0 / interval)),
                    beat_confidence,
                )
            )
        if changes:
            changes.append(
                engine.TempoChange(len(changes), changes[-1].bpm, changes[-1].confidence)
            )
    if not changes:
        changes = [engine.TempoChange(0, float(analysis.get("tempoBpm", 120.0)), confidence)]

    signatures = [
        engine.TimeSignature(
            int(item["numerator"]),
            int(item["denominator"]),
            item.get("startBeat", 0),
            float(item.get("confidence", confidence) or confidence),
        )
        for item in analysis.get("timeSignatures", [])
        if isinstance(item, dict)
        and "numerator" in item
        and "denominator" in item
        and "startSeconds" not in item
    ]
    if not signatures:
        signatures = [
            engine.TimeSignature(
                int(analysis.get("timeSignatureNumerator", 4)),
                int(analysis.get("timeSignatureDenominator", 4)),
                confidence=confidence,
            )
        ]
    return engine.TempoMap(tuple(changes), tuple(signatures), offset_seconds)


def minimal_musicxml(project: Project, transcription: Transcription) -> bytes:
    title = project.title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <work><work-title>{title}</work-title></work>
  <part-list><score-part id="P1"><part-name>Drumset</part-name></score-part></part-list>
  <part id="P1"><measure number="1"><attributes><divisions>4</divisions>
  <time><beats>{transcription.time_signature_numerator}</beats>
  <beat-type>{transcription.time_signature_denominator}</beat-type></time>
  <clef><sign>percussion</sign><line>2</line></clef></attributes>
  <direction><direction-type><metronome><beat-unit>quarter</beat-unit>
  <per-minute>{transcription.tempo_bpm:g}</per-minute></metronome></direction-type></direction>
  <note><rest/><duration>16</duration><type>whole</type></note></measure></part>
</score-partwise>"""
    return xml.encode("utf-8")


class PipelineService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        storage: PrivateStorage,
    ) -> None:
        self.settings = settings
        self.database = database
        self.storage = storage
        self.audio_probe = AudioProbe(settings)
        self.music = MusicEngineAdapter(settings)

    @staticmethod
    def _provider_retention_datetime(metadata: ProviderRunMetadata) -> datetime | None:
        if not metadata.retention_expires_at:
            return None
        try:
            return datetime.fromisoformat(metadata.retention_expires_at.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _record_provider_metadata(
        job: ProcessingJob, stage: str, metadata: ProviderRunMetadata
    ) -> None:
        PipelineService._record_provider_metadata_dict(job, stage, metadata.as_dict())

    @staticmethod
    def _record_provider_metadata_dict(
        job: ProcessingJob, stage: str, metadata: dict[str, Any]
    ) -> None:
        runs = dict(job.provider_metadata or {})
        runs[stage] = metadata
        job.provider_metadata = runs
        cost = metadata.get("cost")
        if not isinstance(cost, dict) or not isinstance(cost.get("amount"), int | float):
            return
        currency = str(cost.get("currency") or "units")
        if job.provider_cost_currency not in {None, currency}:
            job.total_provider_cost = None
            job.provider_cost_currency = "mixed"
            return
        job.provider_cost_currency = currency
        job.total_provider_cost = round(
            float(job.total_provider_cost or 0) + float(cost["amount"]), 8
        )

    async def run(self, job_id: uuid.UUID) -> None:
        async with self.database.session_factory() as db:
            job = (
                await db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
            ).scalar_one_or_none()
            if job is None or job.stage in TERMINAL_JOB_STAGES:
                return
            project = await db.get(Project, job.project_id)
            if project is None or project.deleted_at is not None:
                return
            try:
                while job.stage not in TERMINAL_JOB_STAGES:
                    if job.cancel_requested_at is not None:
                        await transition_job(
                            db, job, JobStage.CANCELLED, worker=socket.gethostname()
                        )
                        project.status = ProjectStatus.CANCELLED
                        await db.commit()
                        return
                    # `stage` is the durable in-progress checkpoint. Commit it before
                    # work begins so an acks-late redelivery reruns, rather than skips,
                    # an interrupted stage.
                    if job.stage == JobStage.RECEIVED:
                        await transition_job(
                            db, job, JobStage.VALIDATING, worker=socket.gethostname()
                        )
                        await db.commit()
                    current_stage = job.stage
                    started = time.monotonic()
                    await self._run_stage(db, job, project, current_stage)
                    timings = dict(job.stage_timings or {})
                    timings[current_stage.value] = round(time.monotonic() - started, 4)
                    job.stage_timings = timings
                    next_stage = STAGE_ORDER[STAGE_ORDER.index(current_stage) + 1]
                    await transition_job(db, job, next_stage, worker=socket.gethostname())
                    if next_stage == JobStage.READY:
                        project.status = ProjectStatus.READY
                    await db.commit()
                    if next_stage == JobStage.READY:
                        return
            except Exception as exc:
                await db.rollback()
                if isinstance(exc, TRANSIENT_PIPELINE_ERRORS):
                    logger.warning(
                        "pipeline_transient_failure",
                        job_id=str(job_id),
                        stage=job.stage.value,
                        error_type=type(exc).__name__,
                    )
                    raise
                job = await db.get(ProcessingJob, job_id)
                project = await db.get(Project, job.project_id) if job else None
                if job and job.stage not in TERMINAL_JOB_STAGES:
                    error_code = self._error_code(exc, job.stage)
                    if isinstance(exc, CommercialProviderError):
                        self._record_provider_metadata(
                            job,
                            job.stage.value,
                            ProviderRunMetadata(
                                provider=self._configured_provider_for_stage(job.stage),
                                category=ProviderCategory.PRODUCTION_COMMERCIAL,
                                model_version="unknown",
                                request_id=exc.request_id,
                                processing_ms=0,
                                error_category=exc.category,
                            ),
                        )
                    if job.stage == JobStage.VALIDATING and project is not None:
                        input_asset_id = self._job_input_asset_id(job, project)
                        failed_asset = (
                            await db.get(AudioAsset, input_asset_id)
                            if input_asset_id is not None
                            else None
                        )
                        if failed_asset is not None and failed_asset.deleted_at is None:
                            failed_asset.status = AssetStatus.REJECTED
                            failed_asset.deleted_at = utcnow()
                            failed_asset.expires_at = utcnow()
                    await transition_job(
                        db,
                        job,
                        JobStage.FAILED,
                        worker=socket.gethostname(),
                        error_code=error_code,
                        error_detail=f"{type(exc).__name__}: {str(exc)[:1000]}",
                    )
                    if (
                        project
                        and self._job_input_asset_id(job, project) == project.original_asset_id
                    ):
                        project.status = ProjectStatus.FAILED
                    await db.commit()
                logger.exception("pipeline_failed", job_id=str(job_id))
                raise

    def _configured_provider_for_stage(self, stage: JobStage) -> str:
        if stage == JobStage.SEPARATING_DRUMS:
            return self.settings.source_separation_provider
        if stage == JobStage.TRANSCRIBING:
            return self.settings.music_transcription_provider
        if stage == JobStage.DETECTING_BEATS:
            return self.settings.beat_tracking_provider
        return "pipeline"

    async def _run_stage(
        self,
        db: AsyncSession,
        job: ProcessingJob,
        project: Project,
        stage: JobStage,
    ) -> None:
        if stage == JobStage.VALIDATING:
            asset = await self._original_asset(db, project, job)
            metadata = await self.storage.head(asset.storage_key)
            if metadata.size_bytes > self.settings.max_upload_bytes:
                raise APIError(413, JobErrorCode.AUDIO_TOO_LARGE.value, "Audio is too large.")
            async with self.storage.materialize(asset.storage_key) as path:
                audio = await self.audio_probe.inspect(
                    path,
                    declared_content_type=asset.content_type or "application/octet-stream",
                    size_bytes=metadata.size_bytes,
                )
            owner = await db.get(User, project.owner_id)
            if (
                owner is not None
                and owner.kind == UserKind.ANONYMOUS
                and audio.duration_seconds > self.settings.anonymous_max_audio_duration_seconds
            ):
                raise APIError(
                    422,
                    JobErrorCode.AUDIO_TOO_LONG.value,
                    (
                        "Anonymous trials currently support up to "
                        f"{self.settings.anonymous_max_audio_duration_seconds:g} seconds. "
                        "Sign in to process a full recording."
                    ),
                )
            asset.status = AssetStatus.VERIFIED
            asset.expires_at = None
            asset.size_bytes = audio.size_bytes
            asset.duration_seconds = audio.duration_seconds
            asset.codec = audio.codec
            asset.sample_rate = audio.sample_rate
            asset.channels = audio.channels
            project.duration_seconds = audio.duration_seconds
            return
        if stage == JobStage.NORMALIZING:
            source = await self._original_asset(db, project, job)
            await self._ensure_normalized(db, project, source, job)
            return
        if stage == JobStage.SEPARATING_DRUMS:
            source = await self._asset(db, project.id, AssetKind.NORMALIZED)
            _, provider_metadata = await self._ensure_drum_stem(db, project, source)
            versions = dict(job.provider_versions or {})
            versions["separation"] = (
                f"{provider_metadata.provider}/{provider_metadata.model_version}"
                if provider_metadata is not None
                else "checkpoint/reused"
            )
            job.provider_versions = versions
            if provider_metadata is not None:
                self._record_provider_metadata(job, "separation", provider_metadata)
            return
        if stage == JobStage.TRANSCRIBING:
            existing = (
                (await db.execute(select(ModelRun).where(ModelRun.job_id == job.id)))
                .scalars()
                .first()
            )
            if existing is not None:
                return
            input_kind = self.music.transcription_input_kind()
            input_asset_kind = (
                AssetKind.NORMALIZED if input_kind == "full_mix" else AssetKind.DRUM_STEM
            )
            transcription_input = await self._asset(db, project.id, input_asset_kind)
            async with self.storage.materialize(transcription_input.storage_key) as path:
                if (
                    self.settings.music_transcription_provider.casefold()
                    == "drumscribe_recall_fusion"
                ):
                    mixture_asset = await self._asset(
                        db, project.id, AssetKind.NORMALIZED
                    )
                    async with self.storage.materialize(
                        mixture_asset.storage_key
                    ) as mixture_path:
                        transcription_result = await self.music.transcribe(
                            path,
                            project.duration_seconds or 8.0,
                            mixture_path=mixture_path,
                        )
                else:
                    transcription_result = await self.music.transcribe(
                        path, project.duration_seconds or 8.0
                    )
            hits = transcription_result.hits
            provider_metadata = transcription_result.metadata
            raw_hit_rows = [
                {
                    "instrument": hit.instrument.value,
                    "onsetSeconds": hit.onset_seconds,
                    "velocity": hit.velocity,
                    "confidence": hit.confidence,
                }
                for hit in hits
            ]
            run = ModelRun(
                job_id=job.id,
                provider=provider_metadata.provider,
                provider_category=provider_metadata.category.value,
                provider_request_id=provider_metadata.request_id,
                model_name=self.settings.music_transcription_provider,
                model_version=provider_metadata.model_version,
                parameters={
                    "canonicalClasses": [item.value for item in Instrument],
                    "inputKind": input_kind,
                    "inputAssetKind": input_asset_kind.value,
                },
                duration_seconds=provider_metadata.processing_ms / 1000,
                summary={"rawHits": raw_hit_rows, "rawHitCount": len(raw_hit_rows)},
                hardware_metadata={"worker": socket.gethostname()},
                raw_provider_metadata=provider_metadata.raw_metadata,
                error_category=(
                    provider_metadata.error_category.value
                    if provider_metadata.error_category
                    else None
                ),
                cost_amount=provider_metadata.cost_amount,
                cost_currency=provider_metadata.cost_currency,
                retention_expires_at=self._provider_retention_datetime(provider_metadata),
                contract_reference=provider_metadata.contract_reference,
            )
            db.add(run)
            versions = dict(job.provider_versions or {})
            versions["transcription"] = (
                f"{provider_metadata.provider}/{provider_metadata.model_version}"
            )
            job.provider_versions = versions
            self._record_provider_metadata(job, "transcription", provider_metadata)
            return
        if stage == JobStage.DETECTING_BEATS:
            run = await self._model_run(db, job.id)
            # The full mix supplies stable pulse/downbeat evidence that may be absent
            # from a sparse or imperfectly separated drum stem.
            normalized = await self._asset(db, project.id, AssetKind.NORMALIZED)
            async with self.storage.materialize(normalized.storage_key) as path:
                beat_analysis = await self.music.track_beats(path)
            summary = dict(run.summary)
            summary["beatAnalysis"] = beat_analysis
            run.summary = summary
            versions = dict(job.provider_versions or {})
            beat_metadata_payload = beat_analysis.get("providerMetadata")
            versions["beatTracking"] = (
                f"{beat_analysis['provider']}/"
                f"{beat_metadata_payload.get('modelVersion', 'unknown')}"
                if isinstance(beat_metadata_payload, dict)
                else str(beat_analysis["provider"])
            )
            job.provider_versions = versions
            if isinstance(beat_metadata_payload, dict):
                self._record_provider_metadata_dict(job, "beatTracking", beat_metadata_payload)
            return
        if stage == JobStage.QUANTIZING:
            existing_transcription = (
                await db.execute(select(Transcription).where(Transcription.source_job_id == job.id))
            ).scalar_one_or_none()
            if existing_transcription is not None:
                project.active_transcription_id = existing_transcription.id
                return
            run = await self._model_run(db, job.id)
            checkpoint_hits = [
                RawDrumHit(
                    instrument=canonical_instrument(raw["instrument"]),
                    onset_seconds=float(raw["onsetSeconds"]),
                    velocity=int(raw["velocity"]),
                    confidence=float(raw["confidence"]),
                )
                for raw in run.summary.get("rawHits", [])
            ]
            checkpoint_analysis = run.summary.get("beatAnalysis")
            if not isinstance(checkpoint_analysis, dict):
                raise RuntimeError("beat-tracking checkpoint missing")
            bpm = float(checkpoint_analysis["tempoBpm"])
            numerator = int(checkpoint_analysis["timeSignatureNumerator"])
            denominator = int(checkpoint_analysis["timeSignatureDenominator"])
            quantized, notation_tempo_map, completion_applied = _quantize_hits_with_tempo(
                checkpoint_hits,
                bpm,
                numerator,
                denominator,
                timing_analysis=checkpoint_analysis,
                rhythm_completion=run.model_name.casefold() == "drumscribe_hybrid",
            )
            low_confidence = sum(1 for item in quantized if (item["confidence"] or 0) < 0.75)
            if completion_applied:
                bpm = float(notation_tempo_map.changes[0].bpm)
                numerator = int(notation_tempo_map.time_signatures[0].numerator)
                denominator = int(notation_tempo_map.time_signatures[0].denominator)
                timing_map = _serialize_engine_tempo_map(notation_tempo_map)
            else:
                timing_map = [
                    *list(checkpoint_analysis.get("tempoMap", [])),
                    *list(checkpoint_analysis.get("timeSignatures", [])),
                    *[
                        {"kind": "beat", **item}
                        for item in checkpoint_analysis.get("beats", [])
                        if isinstance(item, dict)
                    ],
                    {
                        "kind": "offset",
                        "offsetSeconds": float(checkpoint_analysis.get("offsetSeconds", 0)),
                    },
                ]
            transcription = Transcription(
                project_id=project.id,
                source_job_id=job.id,
                tempo_bpm=bpm,
                time_signature_numerator=numerator,
                time_signature_denominator=denominator,
                tempo_map=timing_map,
                timing_ai_baseline=timing_map,
                quality_summary={
                    "message": "Your chart is ready. A few sections may need review.",
                    "eventCount": len(quantized),
                    "lowConfidenceCount": low_confidence,
                    "aiOutputIsApproximate": True,
                    "providerCategories": {
                        stage_name: metadata.get("category")
                        for stage_name, metadata in (job.provider_metadata or {}).items()
                        if isinstance(metadata, dict)
                    },
                },
            )
            db.add(transcription)
            await db.flush()
            for item in quantized:
                db.add(
                    DrumEvent(
                        transcription_id=transcription.id,
                        project_id=project.id,
                        **item,
                    )
                )
            project.active_transcription_id = transcription.id
            project.edit_version = transcription.version
            await db.flush()
            return
        if stage == JobStage.GENERATING_SCORE:
            transcription = await self._transcription(db, project)
            existing_revision = (
                await db.execute(
                    select(1).where(TranscriptionRevision.transcription_id == transcription.id)
                )
            ).first()
            if existing_revision is None:
                await create_revision(
                    db,
                    transcription,
                    kind=RevisionKind.AI_ORIGINAL,
                    label="Original AI transcription",
                    created_by_user_id=None,
                )
            input_asset_id = self._job_input_asset_id(job, project)
            key = (
                f"users/{project.owner_id}/projects/{project.id}/score/"
                f"{input_asset_id}/current.musicxml"
            )
            score_events = list(
                (
                    await db.execute(
                        select(DrumEvent)
                        .where(
                            DrumEvent.transcription_id == transcription.id,
                            DrumEvent.deleted_at.is_(None),
                        )
                        .order_by(DrumEvent.quantized_onset, DrumEvent.id)
                    )
                ).scalars()
            )
            try:
                score = generate_export_bytes(
                    ExportFormat.MUSICXML, score_events, transcription, project
                )
            except ImportError:
                score = minimal_musicxml(project, transcription)
            await self.storage.put_bytes(key, score, "application/vnd.recordare.musicxml+xml")
            score_asset = (
                await db.execute(
                    select(AudioAsset).where(
                        AudioAsset.project_id == project.id,
                        AudioAsset.kind == AssetKind.SCORE_SOURCE,
                        AudioAsset.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if score_asset is None:
                db.add(
                    AudioAsset(
                        project_id=project.id,
                        kind=AssetKind.SCORE_SOURCE,
                        status=AssetStatus.VERIFIED,
                        storage_key=key,
                        content_type="application/vnd.recordare.musicxml+xml",
                        size_bytes=len(score),
                    )
                )
            return
        if stage == JobStage.FINALIZING:
            await self._transcription(db, project)
            await self._ensure_waveform(db, project)
            normalized = await self._asset(db, project.id, AssetKind.NORMALIZED)
            normalized.status = AssetStatus.DELETING
            normalized.deleted_at = utcnow()
            normalized.expires_at = utcnow()
            project.status = ProjectStatus.PROCESSING
            return

    async def _original_asset(
        self, db: AsyncSession, project: Project, job: ProcessingJob
    ) -> AudioAsset:
        asset_id = self._job_input_asset_id(job, project)
        if asset_id is None:
            raise APIError(409, "UPLOAD_REQUIRED", "Upload audio before processing.")
        asset = await db.get(AudioAsset, asset_id)
        if asset is None or asset.deleted_at is not None:
            raise APIError(
                409,
                "UPLOAD_REPLACED",
                "The audio for this job was replaced. Start a new processing job.",
            )
        return asset

    @staticmethod
    def _job_input_asset_id(job: ProcessingJob, project: Project) -> uuid.UUID | None:
        raw_id = (job.provider_versions or {}).get("inputAssetId")
        if raw_id:
            try:
                return uuid.UUID(str(raw_id))
            except ValueError as exc:
                raise RuntimeError("processing job input checkpoint is invalid") from exc
        return project.original_asset_id

    async def _asset(self, db: AsyncSession, project_id: uuid.UUID, kind: AssetKind) -> AudioAsset:
        asset = (
            (
                await db.execute(
                    select(AudioAsset).where(
                        AudioAsset.project_id == project_id,
                        AudioAsset.kind == kind,
                        AudioAsset.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if asset is None:
            raise ObjectNotFoundError(f"{project_id}/{kind.value}")
        return asset

    async def _ensure_normalized(
        self,
        db: AsyncSession,
        project: Project,
        source: AudioAsset,
        job: ProcessingJob,
    ) -> AudioAsset:
        existing = await self._active_asset(db, project.id, AssetKind.NORMALIZED)
        if existing is not None:
            return existing
        key = (
            f"users/{project.owner_id}/projects/{project.id}/working/"
            f"{source.id}/{job.id}/normalized.wav"
        )
        with tempfile.TemporaryDirectory(prefix="drumscribe-normalize-") as directory:
            output = Path(directory) / "normalized.wav"
            async with self.storage.materialize(source.storage_key) as input_path:
                ffmpeg = shutil.which(self.settings.ffmpeg_binary)
                if ffmpeg:
                    engine = self.music._engine()
                    await asyncio.to_thread(
                        engine.normalize_audio,
                        input_path,
                        output,
                        ffmpeg=ffmpeg,
                    )
                elif source.content_type in {"audio/wav", "audio/x-wav", "audio/wave"} and (
                    source.codec or ""
                ).startswith("pcm_"):
                    # A truthful WAV-to-WAV fallback keeps local tests usable when
                    # FFmpeg is absent; compressed inputs are never relabelled.
                    await asyncio.to_thread(shutil.copyfile, input_path, output)
                else:
                    raise RuntimeError("FFmpeg is required to normalize compressed audio.")
            output_size = (await asyncio.to_thread(output.stat)).st_size
            metadata = await self.audio_probe.inspect(
                output,
                declared_content_type="audio/wav",
                size_bytes=output_size,
            )
            await self.storage.put_file(key, output, "audio/wav")
        return await self._upsert_asset(
            db,
            project,
            kind=AssetKind.NORMALIZED,
            key=key,
            content_type=metadata.content_type,
            size_bytes=metadata.size_bytes,
            duration_seconds=metadata.duration_seconds,
            codec=metadata.codec,
            sample_rate=metadata.sample_rate,
            channels=metadata.channels,
        )

    async def _ensure_drum_stem(
        self,
        db: AsyncSession,
        project: Project,
        source: AudioAsset,
    ) -> tuple[AudioAsset, ProviderRunMetadata | None]:
        existing = await self._active_asset(db, project.id, AssetKind.DRUM_STEM)
        if existing is not None:
            return existing, None
        input_asset_id = project.original_asset_id or source.id
        key = f"users/{project.owner_id}/projects/{project.id}/stems/{input_asset_id}/drums.wav"
        with tempfile.TemporaryDirectory(prefix="drumscribe-separate-") as directory:
            output = Path(directory) / "drums.wav"
            async with self.storage.materialize(source.storage_key) as input_path:
                provider_metadata = await self.music.separate(input_path, output)
            output_size = (await asyncio.to_thread(output.stat)).st_size
            metadata = await self.audio_probe.inspect(
                output,
                declared_content_type="audio/wav",
                size_bytes=output_size,
            )
            await self.storage.put_file(key, output, "audio/wav")
        asset = await self._upsert_asset(
            db,
            project,
            kind=AssetKind.DRUM_STEM,
            key=key,
            content_type=metadata.content_type,
            size_bytes=metadata.size_bytes,
            duration_seconds=metadata.duration_seconds,
            codec=metadata.codec,
            sample_rate=metadata.sample_rate,
            channels=metadata.channels,
        )
        return asset, provider_metadata

    async def _active_asset(
        self, db: AsyncSession, project_id: uuid.UUID, kind: AssetKind
    ) -> AudioAsset | None:
        return (
            (
                await db.execute(
                    select(AudioAsset).where(
                        AudioAsset.project_id == project_id,
                        AudioAsset.kind == kind,
                        AudioAsset.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )

    async def _upsert_asset(
        self,
        db: AsyncSession,
        project: Project,
        *,
        kind: AssetKind,
        key: str,
        content_type: str,
        size_bytes: int,
        duration_seconds: float,
        codec: str,
        sample_rate: int | None,
        channels: int | None,
    ) -> AudioAsset:
        asset = (
            await db.execute(select(AudioAsset).where(AudioAsset.storage_key == key))
        ).scalar_one_or_none()
        if asset is None:
            asset = AudioAsset(project_id=project.id, kind=kind, storage_key=key)
            db.add(asset)
        asset.status = AssetStatus.VERIFIED
        asset.deleted_at = None
        asset.expires_at = None
        asset.content_type = content_type
        asset.size_bytes = size_bytes
        asset.duration_seconds = duration_seconds
        asset.codec = codec
        asset.sample_rate = sample_rate
        asset.channels = channels
        await db.flush()
        return asset

    async def _model_run(self, db: AsyncSession, job_id: uuid.UUID) -> ModelRun:
        run = (
            (await db.execute(select(ModelRun).where(ModelRun.job_id == job_id))).scalars().first()
        )
        if run is None:
            raise RuntimeError("transcription checkpoint missing")
        return run

    async def _ensure_waveform(self, db: AsyncSession, project: Project) -> AudioAsset:
        existing = (
            (
                await db.execute(
                    select(AudioAsset).where(
                        AudioAsset.project_id == project.id,
                        AudioAsset.kind == AssetKind.WAVEFORM_PEAKS,
                        AudioAsset.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return existing
        normalized = await self._asset(db, project.id, AssetKind.NORMALIZED)
        try:
            engine = importlib.import_module("drumscribe_music")
            async with self.storage.materialize(normalized.storage_key) as path:
                peaks = await asyncio.to_thread(engine.generate_waveform_peaks, path, bins=2_000)
                data = engine.waveform_peaks_json(peaks)
        except (ImportError, OSError, ValueError, RuntimeError):
            # Non-WAV development inputs still get a valid, explicit empty envelope.
            data = json.dumps(
                {
                    "durationSeconds": project.duration_seconds or 0,
                    "channels": normalized.channels,
                    "sampleRate": normalized.sample_rate,
                    "peaks": [],
                },
                separators=(",", ":"),
            ).encode()
        input_asset_id = project.original_asset_id or normalized.id
        key = f"users/{project.owner_id}/projects/{project.id}/waveform/{input_asset_id}/peaks.json"
        await self.storage.put_bytes(key, data, "application/json")
        asset = AudioAsset(
            project_id=project.id,
            kind=AssetKind.WAVEFORM_PEAKS,
            status=AssetStatus.VERIFIED,
            storage_key=key,
            content_type="application/json",
            size_bytes=len(data),
            duration_seconds=project.duration_seconds,
        )
        db.add(asset)
        await db.flush()
        return asset

    async def _transcription(self, db: AsyncSession, project: Project) -> Transcription:
        if project.active_transcription_id is None:
            raise RuntimeError("quantization checkpoint missing")
        transcription = await db.get(Transcription, project.active_transcription_id)
        if transcription is None:
            raise RuntimeError("active transcription missing")
        return transcription

    @staticmethod
    def _error_code(exc: Exception, stage: JobStage) -> JobErrorCode:
        if isinstance(exc, APIError):
            try:
                return JobErrorCode(exc.code)
            except ValueError:
                return JobErrorCode.INTERNAL_ERROR
        return {
            JobStage.VALIDATING: JobErrorCode.INVALID_AUDIO,
            JobStage.SEPARATING_DRUMS: JobErrorCode.SEPARATION_FAILED,
            JobStage.TRANSCRIBING: JobErrorCode.TRANSCRIPTION_FAILED,
            JobStage.DETECTING_BEATS: JobErrorCode.BEAT_TRACKING_FAILED,
            JobStage.QUANTIZING: JobErrorCode.BEAT_TRACKING_FAILED,
            JobStage.GENERATING_SCORE: JobErrorCode.SCORE_GENERATION_FAILED,
        }.get(stage, JobErrorCode.INTERNAL_ERROR)
