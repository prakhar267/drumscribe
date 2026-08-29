"""Musical quantization that preserves raw performance timing and close articulations."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from statistics import median

from .mapping import canonical_instrument
from .models import DrumEvent, EventSource, GridSubdivision, RawDrumHit
from .tempo import TempoMap, _round_fraction

DEFAULT_SUBDIVISIONS = (
    GridSubdivision.QUARTER,
    GridSubdivision.EIGHTH,
    GridSubdivision.SIXTEENTH,
    GridSubdivision.EIGHTH_TRIPLET,
    GridSubdivision.THIRTY_SECOND,
    GridSubdivision.SIXTEENTH_TRIPLET,
)


@dataclass(frozen=True, slots=True)
class QuantizationSettings:
    subdivisions: tuple[GridSubdivision, ...] = DEFAULT_SUBDIVISIONS
    max_snap_seconds: float = 0.125
    simultaneity_tolerance_seconds: float = 0.025
    duplicate_tolerance_seconds: float = 0.008
    flam_tolerance_seconds: float = 0.085
    preserve_flams: bool = True

    def __post_init__(self) -> None:
        if not self.subdivisions:
            raise ValueError("at least one subdivision is required")
        if len(set(self.subdivisions)) != len(self.subdivisions):
            raise ValueError("subdivisions must be unique")
        for name in (
            "max_snap_seconds",
            "simultaneity_tolerance_seconds",
            "duplicate_tolerance_seconds",
            "flam_tolerance_seconds",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.duplicate_tolerance_seconds > self.flam_tolerance_seconds:
            raise ValueError("duplicate tolerance cannot exceed flam tolerance")


_COMPLEXITY_PENALTY_SECONDS = {
    GridSubdivision.QUARTER: 0.000,
    GridSubdivision.EIGHTH: 0.001,
    GridSubdivision.SIXTEENTH: 0.003,
    GridSubdivision.EIGHTH_TRIPLET: 0.008,
    GridSubdivision.THIRTY_SECOND: 0.011,
    GridSubdivision.SIXTEENTH_TRIPLET: 0.014,
}


def deduplicate_raw_hits(
    hits: Iterable[RawDrumHit], tolerance_seconds: float = 0.008
) -> list[RawDrumHit]:
    """Collapse detector double-fires while retaining plausible flams."""

    ordered = sorted(hits, key=lambda hit: (hit.onset_seconds, str(hit.instrument_class)))
    result: list[RawDrumHit] = []
    for hit in ordered:
        instrument = canonical_instrument(hit.instrument_class)
        duplicate_index = next(
            (
                index
                for index in range(len(result) - 1, -1, -1)
                if hit.onset_seconds - result[index].onset_seconds <= tolerance_seconds
                and canonical_instrument(result[index].instrument_class) == instrument
            ),
            None,
        )
        if duplicate_index is None:
            result.append(hit)
        elif hit.confidence > result[duplicate_index].confidence:
            result[duplicate_index] = hit
    return sorted(result, key=lambda hit: hit.onset_seconds)


class DefaultQuantizer:
    def __init__(self, settings: QuantizationSettings | None = None) -> None:
        self.settings = settings or QuantizationSettings()

    def quantize(
        self,
        hits: Iterable[RawDrumHit],
        tempo_map: TempoMap,
        project_id: str | None = None,
    ) -> list[DrumEvent]:
        raw = deduplicate_raw_hits(hits, self.settings.duplicate_tolerance_seconds)
        anchors = self._simultaneous_anchors(raw)
        events: list[DrumEvent] = []
        for hit, anchor in zip(raw, anchors, strict=True):
            beat, subdivision, quantized_seconds = self._best_grid(anchor, tempo_map)
            if beat < 0 or abs(quantized_seconds - anchor) > self.settings.max_snap_seconds:
                # Still retain a rational location, but avoid a large audio-time jump.
                beat = max(Fraction(0), tempo_map.seconds_to_beat(anchor).limit_denominator(960))
                quantized_seconds = tempo_map.beat_to_seconds(beat)
                subdivision = None
            position = tempo_map.beat_to_position(beat)
            events.append(
                DrumEvent(
                    project_id=project_id,
                    instrument=canonical_instrument(hit.instrument_class),
                    onset_seconds=hit.onset_seconds,
                    duration_seconds=hit.duration_seconds,
                    velocity=hit.velocity,
                    confidence=hit.confidence,
                    source=EventSource.TRANSCRIPTION,
                    beat_position=beat,
                    measure_index=position.measure_index,
                    beat_in_measure=position.beat_in_measure,
                    subdivision=subdivision,
                    quantized_onset_seconds=quantized_seconds,
                )
            )
        return self._mark_grace_events(events)

    def _best_grid(
        self, seconds: float, tempo_map: TempoMap
    ) -> tuple[Fraction, GridSubdivision | None, float]:
        source_beat = tempo_map.seconds_to_beat(seconds)
        best: tuple[float, int, Fraction, GridSubdivision, float] | None = None
        for rank, subdivision in enumerate(self.settings.subdivisions):
            step = subdivision.beats
            candidate_beat = _round_fraction(source_beat / step) * step
            candidate_seconds = tempo_map.beat_to_seconds(candidate_beat)
            score = abs(candidate_seconds - seconds) + _COMPLEXITY_PENALTY_SECONDS[subdivision]
            item = (score, rank, candidate_beat, subdivision, candidate_seconds)
            if best is None or item < best:
                best = item
        assert best is not None
        return best[2], best[3], best[4]

    def _simultaneous_anchors(self, hits: Sequence[RawDrumHit]) -> list[float]:
        anchors = [hit.onset_seconds for hit in hits]
        start = 0
        while start < len(hits):
            end = start + 1
            instruments = {canonical_instrument(hits[start].instrument_class)}
            while end < len(hits):
                next_instrument = canonical_instrument(hits[end].instrument_class)
                if (
                    hits[end].onset_seconds - hits[start].onset_seconds
                    > self.settings.simultaneity_tolerance_seconds
                    or next_instrument in instruments
                ):
                    break
                instruments.add(next_instrument)
                end += 1
            if end - start > 1:
                anchor = float(median(hit.onset_seconds for hit in hits[start:end]))
                anchors[start:end] = [anchor] * (end - start)
            start = end
        return anchors

    def _mark_grace_events(self, events: list[DrumEvent]) -> list[DrumEvent]:
        if not self.settings.preserve_flams:
            return events
        result = list(events)
        by_instrument: dict[object, list[int]] = {}
        for index, event in enumerate(events):
            by_instrument.setdefault(event.instrument, []).append(index)
        for indices in by_instrument.values():
            for left, right in zip(indices, indices[1:], strict=False):
                first, second = result[left], result[right]
                delta = second.onset_seconds - first.onset_seconds
                if (
                    self.settings.duplicate_tolerance_seconds
                    < delta
                    <= self.settings.flam_tolerance_seconds
                    and first.beat_position == second.beat_position
                ):
                    result[left] = first.edited(
                        is_grace=True,
                        grace_of_event_id=second.id,
                        manually_edited=False,
                    )
        return result


def quantize_hits(
    hits: Iterable[RawDrumHit],
    tempo_map: TempoMap,
    *,
    project_id: str | None = None,
    settings: QuantizationSettings | None = None,
) -> list[DrumEvent]:
    return DefaultQuantizer(settings).quantize(hits, tempo_map, project_id)
