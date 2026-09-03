"""Confidence-gated rhythmic completion for readable drum notation drafts."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from statistics import linear_regression, median
from typing import Any

from .mapping import canonical_instrument
from .models import Instrument, RawDrumHit
from .tempo import TempoChange, TempoMap

_FAMILIES = {
    "KICK": frozenset({Instrument.KICK}),
    "SNARE": frozenset({Instrument.SNARE, Instrument.CROSS_STICK}),
    "HIHAT": frozenset({Instrument.CLOSED_HIHAT, Instrument.OPEN_HIHAT, Instrument.PEDAL_HIHAT}),
    "CYMBAL": frozenset({Instrument.CRASH, Instrument.RIDE, Instrument.RIDE_BELL}),
    "TOM": frozenset(
        {
            Instrument.HIGH_TOM,
            Instrument.MID_TOM,
            Instrument.LOW_TOM,
            Instrument.FLOOR_TOM,
        }
    ),
    "TAMBOURINE": frozenset({Instrument.TAMBOURINE}),
}
_FAMILY_BY_INSTRUMENT = {
    instrument: family for family, instruments in _FAMILIES.items() for instrument in instruments
}
_PATTERNS = (
    ("quarter", frozenset({0, 4, 8, 12})),
    ("offbeat", frozenset({2, 6, 10, 14})),
    ("eighth", frozenset(range(0, 16, 2))),
    ("swing", frozenset({0, 3, 4, 7, 8, 11, 12, 15})),
    ("sixteenth", frozenset(range(16))),
)


@dataclass(frozen=True, slots=True)
class RhythmCompletionSettings:
    """Parameters frozen on the cross-genre development split."""

    detector_latency_seconds: float = 0.008368806451612976
    minimum_kick_anchors: int = 4
    minimum_anchor_confidence: float = 0.75
    anchor_assignment_tolerance_seconds: float = 0.060
    maximum_affine_residual_seconds: float = 0.025
    snap_tolerance_seconds: float = 0.055
    pattern_coverage: float = 0.82
    offbeat_signature_coverage: float = 0.75
    texture_dominance_ratio: float = 1.5
    texture_slot_measure_ratio: float = 0.45
    recurring_snare_measure_ratio: float = 0.55

    def __post_init__(self) -> None:
        for name in (
            "detector_latency_seconds",
            "anchor_assignment_tolerance_seconds",
            "maximum_affine_residual_seconds",
            "snap_tolerance_seconds",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.minimum_kick_anchors < 2:
            raise ValueError("minimum_kick_anchors must be at least two")
        if not 0 <= self.minimum_anchor_confidence <= 1:
            raise ValueError("minimum_anchor_confidence must be between zero and one")
        if not 0 < self.pattern_coverage <= 1:
            raise ValueError("pattern_coverage must be between zero and one")
        if not 0 < self.offbeat_signature_coverage <= 1:
            raise ValueError("offbeat_signature_coverage must be between zero and one")
        if self.texture_dominance_ratio < 1:
            raise ValueError("texture_dominance_ratio must be at least one")
        if not 0 < self.texture_slot_measure_ratio <= 1:
            raise ValueError("texture_slot_measure_ratio must be between zero and one")
        if not 0 < self.recurring_snare_measure_ratio <= 1:
            raise ValueError("recurring_snare_measure_ratio must be between zero and one")


@dataclass(frozen=True, slots=True)
class RhythmCompletionResult:
    hits: tuple[RawDrumHit, ...]
    tempo_map: TempoMap
    applied: bool
    metadata: Mapping[str, Any]


def _grid_index(seconds: float, tempo_map: TempoMap) -> int:
    return max(0, round(float(tempo_map.seconds_to_beat(seconds)) * 4))


def _grid_seconds(index: int, tempo_map: TempoMap) -> float:
    return tempo_map.beat_to_seconds(Fraction(index, 4))


def _refine_tempo(
    hits: list[RawDrumHit], tempo_map: TempoMap, settings: RhythmCompletionSettings
) -> tuple[TempoMap, dict[str, Any]] | None:
    kick_hits = sorted(
        (
            hit
            for hit in hits
            if canonical_instrument(hit.instrument_class) is Instrument.KICK
            and hit.confidence >= settings.minimum_anchor_confidence
        ),
        key=lambda hit: hit.onset_seconds,
    )
    anchors_by_index: dict[int, RawDrumHit] = {}
    for hit in kick_hits:
        index = _grid_index(hit.onset_seconds, tempo_map)
        error = hit.onset_seconds - _grid_seconds(index, tempo_map)
        if abs(error) > settings.anchor_assignment_tolerance_seconds:
            continue
        previous = anchors_by_index.get(index)
        if previous is None or hit.confidence > previous.confidence:
            anchors_by_index[index] = hit
    anchors = sorted((index, hit.onset_seconds) for index, hit in anchors_by_index.items())
    candidates: list[tuple[float, float, float, int, str]] = []
    slopes = [
        (right_seconds - left_seconds) / (right_index - left_index)
        for position, (left_index, left_seconds) in enumerate(anchors)
        for right_index, right_seconds in anchors[position + 1 :]
        if 4 <= right_index - left_index <= 64
    ]
    if len(anchors) >= settings.minimum_kick_anchors and slopes:
        tracker_slope = median(slopes)
        tracker_intercept = median(seconds - tracker_slope * index for index, seconds in anchors)
        tracker_residual = median(
            abs(seconds - (tracker_intercept + tracker_slope * index)) for index, seconds in anchors
        )
        candidates.append(
            (
                tracker_residual,
                tracker_slope,
                tracker_intercept,
                len(anchors),
                "tracker_indexed",
            )
        )

    # Beat trackers can miss a beat halfway through a steady track. Reconstructing
    # integer steps from adjacent kick gaps gives an independent, slip-resistant fit.
    tracked_bpm = median(change.bpm for change in tempo_map.changes)
    nominal_step = 15 / tracked_bpm
    kick_times: list[float] = []
    for hit in kick_hits:
        if not kick_times or hit.onset_seconds - kick_times[-1] > 0.050:
            kick_times.append(hit.onset_seconds)
    if len(kick_times) >= settings.minimum_kick_anchors:
        cumulative: list[tuple[int, float]] = [
            (_grid_index(kick_times[0], tempo_map), kick_times[0])
        ]
        cumulative_index = cumulative[0][0]
        for previous, current in zip(kick_times, kick_times[1:], strict=False):
            cumulative_index += max(1, round((current - previous) / nominal_step))
            cumulative.append((cumulative_index, current))
        fit = linear_regression(
            [index for index, _ in cumulative],
            [seconds for _, seconds in cumulative],
        )
        first_residuals = [
            abs(seconds - (fit.intercept + fit.slope * index)) for index, seconds in cumulative
        ]
        median_residual = median(first_residuals)
        retained = [
            point
            for point, error in zip(cumulative, first_residuals, strict=True)
            if error <= max(0.030, 4 * median_residual)
        ]
        if len(retained) >= settings.minimum_kick_anchors:
            fit = linear_regression(
                [index for index, _ in retained],
                [seconds for _, seconds in retained],
            )
            cumulative_residual = median(
                abs(seconds - (fit.intercept + fit.slope * index)) for index, seconds in retained
            )
            candidates.append(
                (
                    cumulative_residual,
                    fit.slope,
                    fit.intercept,
                    len(retained),
                    "cumulative_kick_grid",
                )
            )
    if not candidates:
        return None
    residual, seconds_per_sixteenth, raw_intercept, anchor_count, fit_method = min(candidates)
    if seconds_per_sixteenth <= 0:
        return None
    if residual > settings.maximum_affine_residual_seconds:
        return None

    bpm = 15 / seconds_per_sixteenth
    if not 0.8 * tracked_bpm <= bpm <= 1.2 * tracked_bpm:
        return None
    offset = raw_intercept + settings.detector_latency_seconds
    if offset < 0:
        return None
    refined = TempoMap(
        (TempoChange(0, bpm, min(1.0, tempo_map.changes[0].confidence)),),
        tempo_map.time_signatures,
        offset,
    )
    return refined, {
        "anchorCount": anchor_count,
        "detectorLatencySeconds": settings.detector_latency_seconds,
        "fitMethod": fit_method,
        "fitResidualSeconds": residual,
        "refinedBpm": bpm,
        "refinedOffsetSeconds": offset,
    }


def _generated_hit(
    instrument: Instrument,
    index: int,
    tempo_map: TempoMap,
    *,
    confidence: float,
    velocity: int,
) -> RawDrumHit:
    return RawDrumHit(
        instrument,
        _grid_seconds(index, tempo_map),
        velocity,
        confidence,
        metadata={"rhythmCompletion": "inferred"},
    )


def _pattern(observed: list[int], settings: RhythmCompletionSettings) -> tuple[str, frozenset[int]]:
    for name, slots in _PATTERNS:
        coverage = sum(slot in slots for slot in observed) / len(observed)
        if coverage >= settings.pattern_coverage:
            return name, slots
    return _PATTERNS[-1]


def _hat_instrument(cells: Mapping[tuple[str, int], RawDrumHit], slot: int) -> Instrument:
    votes = Counter(
        canonical_instrument(hit.instrument_class)
        for (family, index), hit in cells.items()
        if family == "HIHAT" and index % 16 == slot
    )
    total = sum(votes.values())
    if total and votes[Instrument.OPEN_HIHAT] >= 2 and votes[Instrument.OPEN_HIHAT] / total >= 0.60:
        return Instrument.OPEN_HIHAT
    return Instrument.CLOSED_HIHAT


def complete_rhythm(
    hits: Iterable[RawDrumHit],
    tempo_map: TempoMap,
    *,
    settings: RhythmCompletionSettings | None = None,
) -> RhythmCompletionResult:
    """Snap reliable hits and fill only strongly repeated hi-hat/snare patterns.

    The method deliberately fails open to the detector output when a stable grid
    cannot be fitted from at least four kick anchors. This prevents the notation
    prior from inventing a groove on sparse, rubato, or tempo-changing material.
    """

    configuration = settings or RhythmCompletionSettings()
    original = sorted(hits, key=lambda hit: hit.onset_seconds)
    refinement = _refine_tempo(original, tempo_map, configuration)
    if refinement is None:
        return RhythmCompletionResult(
            tuple(original), tempo_map, False, {"reason": "unstable_or_sparse_grid"}
        )
    refined_tempo, evidence = refinement

    cells: dict[tuple[str, int], RawDrumHit] = {}
    preserved_hits: list[RawDrumHit] = []
    maximum_index = 0
    for hit in original:
        instrument = canonical_instrument(hit.instrument_class)
        family = _FAMILY_BY_INSTRUMENT.get(instrument)
        if family is None:
            preserved_hits.append(hit)
            continue
        index = _grid_index(hit.onset_seconds, refined_tempo)
        snapped = _grid_seconds(index, refined_tempo)
        if abs(snapped - hit.onset_seconds) > configuration.snap_tolerance_seconds:
            # Expressive off-grid events are detector evidence, not completion
            # candidates. Preserve them at their original onset instead of
            # silently deleting ghost notes, flams, and loose jazz timing.
            preserved_hits.append(hit)
            continue
        maximum_index = max(maximum_index, index)
        candidate = RawDrumHit(
            instrument,
            snapped,
            hit.velocity,
            hit.confidence,
            hit.duration_seconds,
            {**dict(hit.metadata), "originalOnsetSeconds": hit.onset_seconds},
        )
        key = (family, index)
        previous = cells.get(key)
        if previous is None or candidate.confidence > previous.confidence:
            cells[key] = candidate
    if not cells:
        return RhythmCompletionResult(
            tuple(original), tempo_map, False, {"reason": "no_grid_aligned_hits"}
        )

    measure_count = maximum_index // 16 + 1
    occupancy: dict[str, defaultdict[int, set[int]]] = {
        family: defaultdict(set) for family in _FAMILIES
    }
    for family, index in cells:
        occupancy[family][index // 16].add(index % 16)

    hihat_total = sum(len(occupancy["HIHAT"][measure]) for measure in range(measure_count))
    cymbal_total = sum(len(occupancy["CYMBAL"][measure] - {0}) for measure in range(measure_count))
    dominant_texture = "H" if hihat_total >= cymbal_total else "C"
    labels: list[str] = []
    ratio = configuration.texture_dominance_ratio
    for measure in range(measure_count):
        hihat_count = len(occupancy["HIHAT"][measure])
        cymbal_count = len(occupancy["CYMBAL"][measure] - {0})
        if hihat_count >= 2 and hihat_count >= ratio * cymbal_count:
            labels.append("H")
        elif cymbal_count >= 2 and cymbal_count >= ratio * hihat_count:
            labels.append("C")
        else:
            labels.append(dominant_texture)

    templates: dict[str, tuple[str, frozenset[int]]] = {}
    for label, family in (("H", "HIHAT"), ("C", "CYMBAL")):
        measures = [index for index, value in enumerate(labels) if value == label]
        slot_counts = Counter(slot for measure in measures for slot in occupancy[family][measure])
        minimum_slot_measures = max(
            2,
            round(len(measures) * configuration.texture_slot_measure_ratio),
        )
        # Infer a repeated texture only from slots that recur across measures.
        # Without this gate, isolated cymbal false positives can force the
        # template to a dense sixteenth-note ride pattern and create many more
        # false positives than the detector supplied.
        observed = [slot for slot, count in slot_counts.items() if count >= minimum_slot_measures]
        if observed:
            templates[label] = _pattern(observed, configuration)

    # A four-on-the-floor kick pattern plus non-snare offbeat hat evidence is the
    # reliable signature for a true offbeat-only texture. Requiring three distinct
    # kick slots avoids turning sparse ballad/country hats into this pattern.
    hihat_observed_without_snare = [
        index % 16 for family, index in cells if family == "HIHAT" and ("SNARE", index) not in cells
    ]
    kick_observations = [index % 16 for family, index in cells if family == "KICK"]
    quarter_kick_slots = {slot for slot in kick_observations if slot in {0, 4, 8, 12}}
    open_hats = sum(
        canonical_instrument(hit.instrument_class) is Instrument.OPEN_HIHAT
        for (family, index), hit in cells.items()
        if family == "HIHAT" and ("SNARE", index) not in cells
    )
    if (
        "H" in templates
        and len(quarter_kick_slots) >= 3
        and sum(slot in {0, 4, 8, 12} for slot in kick_observations) / len(kick_observations)
        >= 0.80
        and len(hihat_observed_without_snare) >= 8
        and sum(slot in {2, 6, 10, 14} for slot in hihat_observed_without_snare)
        / len(hihat_observed_without_snare)
        >= configuration.offbeat_signature_coverage
        and open_hats / len(hihat_observed_without_snare) < 0.60
    ):
        templates["H"] = ("offbeat", frozenset({2, 6, 10, 14}))

    retained_crashes: list[tuple[int, RawDrumHit]] = []
    for (family, index), hit in cells.items():
        if (
            family == "CYMBAL"
            and canonical_instrument(hit.instrument_class) is Instrument.CRASH
            and hit.confidence >= 0.75
        ):
            retained_crashes.append((index, hit))
    hat_instruments = {slot: _hat_instrument(cells, slot) for slot in range(16)}

    for measure, label in enumerate(labels):
        selected_family = "HIHAT" if label == "H" else "CYMBAL"
        other_family = "CYMBAL" if label == "H" else "HIHAT"
        template = templates.get(label)
        if template is None:
            # No repeated texture was proved for this label. Failing open here
            # is essential: removing detector hits without a replacement
            # pattern destroys quiet and expressive performances.
            continue
        for key in list(cells):
            family, index = key
            if index // 16 != measure:
                continue
            if family == selected_family or (family == other_family and index % 16 != 0):
                del cells[key]
        _, slots = template
        for slot in slots:
            index = measure * 16 + slot
            if index > maximum_index + 2:
                continue
            instrument = hat_instruments[slot] if label == "H" else Instrument.RIDE
            cells[(selected_family, index)] = _generated_hit(
                instrument,
                index,
                refined_tempo,
                confidence=0.70,
                velocity=80,
            )

    # A stable swing ride pattern is sufficient evidence for the conventional
    # backbeat pedal-hat layer, even when separation hides those quiet closures.
    if templates.get("C", (None, frozenset()))[0] == "swing" and labels.count("C") >= max(
        2, measure_count // 2
    ):
        for measure, label in enumerate(labels):
            if label != "C":
                continue
            for slot in (4, 12):
                index = measure * 16 + slot
                cells[("HIHAT", index)] = _generated_hit(
                    Instrument.PEDAL_HIHAT,
                    index,
                    refined_tempo,
                    confidence=0.65,
                    velocity=65,
                )

    snare_counts = Counter(
        slot for measure in range(measure_count) for slot in occupancy["SNARE"][measure]
    )
    minimum_measures = max(2, round(measure_count * configuration.recurring_snare_measure_ratio))
    recurring_snares = {slot for slot, count in snare_counts.items() if count >= minimum_measures}
    if (
        sum(snare_counts.values()) == 1
        and set(snare_counts) <= {4, 12}
        and templates.get("H", (None, frozenset()))[0] in {"offbeat", "eighth", "sixteenth"}
        and measure_count >= 4
    ):
        recurring_snares = {4, 12}
    raw_snare_instruments = Counter(
        canonical_instrument(hit.instrument_class)
        for (family, _), hit in cells.items()
        if family == "SNARE"
    )
    snare_instrument = (
        Instrument.CROSS_STICK
        if raw_snare_instruments[Instrument.CROSS_STICK] > raw_snare_instruments[Instrument.SNARE]
        else Instrument.SNARE
    )
    for measure in range(measure_count):
        for slot in recurring_snares:
            index = measure * 16 + slot
            if index <= maximum_index + 2:
                cells.setdefault(
                    ("SNARE", index),
                    _generated_hit(
                        snare_instrument,
                        index,
                        refined_tempo,
                        confidence=0.70,
                        velocity=90,
                    ),
                )

    completed = [*cells.values(), *preserved_hits]
    occupied_instruments = {
        (canonical_instrument(hit.instrument_class), _grid_index(hit.onset_seconds, refined_tempo))
        for hit in completed
    }
    for index, crash in retained_crashes:
        key = (Instrument.CRASH, index)
        if key not in occupied_instruments:
            completed.append(crash)
            occupied_instruments.add(key)
    completed.sort(
        key=lambda hit: (hit.onset_seconds, str(canonical_instrument(hit.instrument_class)))
    )
    return RhythmCompletionResult(
        tuple(completed),
        refined_tempo,
        True,
        {
            **evidence,
            "inputHitCount": len(original),
            "outputHitCount": len(completed),
            "texturePatterns": {label: pattern[0] for label, pattern in templates.items()},
        },
    )
