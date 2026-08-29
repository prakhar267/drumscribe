from __future__ import annotations

from collections.abc import Iterable

from ..models import DrumEvent
from ..tempo import TempoMap
from .midi import generate_midi, write_midi
from .musicxml import generate_musicxml, write_musicxml
from .pdf import generate_pdf, write_pdf


class StandardNotationProvider:
    provider_id = "drumscribe-standard-export-v1"

    def musicxml(self, events: Iterable[DrumEvent], tempo_map: TempoMap, **metadata: str) -> bytes:
        return generate_musicxml(events, tempo_map, **metadata)

    def midi(self, events: Iterable[DrumEvent], tempo_map: TempoMap) -> bytes:
        return generate_midi(events, tempo_map)

    def pdf(self, events: Iterable[DrumEvent], tempo_map: TempoMap, **metadata: str) -> bytes:
        return generate_pdf(events, tempo_map, **metadata)


__all__ = [
    "StandardNotationProvider",
    "generate_midi",
    "generate_musicxml",
    "generate_pdf",
    "write_midi",
    "write_musicxml",
    "write_pdf",
]
