"""Replaceable boundaries for every analysis stage."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import DrumEvent, RawDrumHit
from .tempo import TempoMap


@runtime_checkable
class SourceSeparationProvider(Protocol):
    provider_id: str

    def separate_drums(self, source: Path, destination: Path) -> Path: ...


@runtime_checkable
class DrumTranscriptionProvider(Protocol):
    provider_id: str

    def transcribe(self, audio_path: Path) -> list[RawDrumHit]: ...


@runtime_checkable
class BeatTrackingProvider(Protocol):
    provider_id: str

    def track(self, audio_path: Path) -> TempoMap: ...


@runtime_checkable
class QuantizationProvider(Protocol):
    def quantize(
        self,
        hits: Iterable[RawDrumHit],
        tempo_map: TempoMap,
        project_id: str | None = None,
    ) -> list[DrumEvent]: ...


@runtime_checkable
class NotationProvider(Protocol):
    provider_id: str

    def musicxml(
        self, events: Iterable[DrumEvent], tempo_map: TempoMap, **metadata: str
    ) -> bytes: ...

    def midi(self, events: Iterable[DrumEvent], tempo_map: TempoMap) -> bytes: ...

    def pdf(self, events: Iterable[DrumEvent], tempo_map: TempoMap, **metadata: str) -> bytes: ...


@runtime_checkable
class CommercialDrumTranscriptionProvider(DrumTranscriptionProvider, Protocol):
    """Marker protocol for a contract-backed future production provider."""

    commercial_license_confirmed: bool
