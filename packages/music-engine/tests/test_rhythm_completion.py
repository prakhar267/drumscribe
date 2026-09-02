from fractions import Fraction

import pytest

from drumscribe_music import (
    Instrument,
    RawDrumHit,
    RhythmCompletionSettings,
    TempoChange,
    TempoMap,
    complete_rhythm,
)


def _detected(instrument: Instrument, index: int, *, latency: float = -0.01) -> RawDrumHit:
    return RawDrumHit(instrument, 0.25 + index * 0.125 + latency, confidence=0.95)


def test_completion_is_a_noop_without_enough_kick_anchors() -> None:
    hits = [_detected(Instrument.KICK, 0), _detected(Instrument.SNARE, 4)]
    tracked = TempoMap.constant(120, offset_seconds=0.30)

    result = complete_rhythm(hits, tracked)

    assert result.applied is False
    assert result.hits == tuple(sorted(hits, key=lambda hit: hit.onset_seconds))
    assert result.tempo_map == tracked


def test_completion_refines_grid_and_fills_repeated_rock_texture() -> None:
    hits = [
        *[_detected(Instrument.KICK, index) for index in (0, 8, 16, 24, 32, 40)],
        *[_detected(Instrument.CLOSED_HIHAT, index) for index in (0, 4, 8, 16, 20, 28, 32, 36, 40)],
        *[_detected(Instrument.SNARE, index) for index in (4, 12, 20, 28, 36, 44)],
    ]
    tracked = TempoMap.constant(120, offset_seconds=0.30)
    settings = RhythmCompletionSettings(detector_latency_seconds=0.01)

    result = complete_rhythm(hits, tracked, settings=settings)

    assert result.applied is True
    assert result.tempo_map.changes[0].bpm == pytest.approx(120)
    assert result.tempo_map.offset_seconds == pytest.approx(0.25)
    hats = [hit for hit in result.hits if hit.instrument_class == Instrument.CLOSED_HIHAT]
    assert len(hats) == 12
    assert {result.tempo_map.seconds_to_beat(hit.onset_seconds) for hit in hats} == {
        Fraction(index, 1) for index in range(12)
    }
    assert len([hit for hit in result.hits if hit.instrument_class == Instrument.SNARE]) == 6


def test_completion_infers_pedal_hats_only_from_stable_swing_ride() -> None:
    swing_slots = (0, 3, 4, 7, 8, 11, 12, 15)
    hits = [
        *[_detected(Instrument.KICK, index) for index in (0, 8, 16, 24, 32, 40)],
        *[
            _detected(Instrument.RIDE, measure * 16 + slot)
            for measure in range(3)
            for slot in swing_slots
            if (measure + slot) % 3 != 1
        ],
        *[_detected(Instrument.SNARE, index) for index in (4, 12, 20, 28, 36, 44)],
    ]

    result = complete_rhythm(
        hits,
        TempoMap.constant(120, offset_seconds=0.30),
        settings=RhythmCompletionSettings(detector_latency_seconds=0.01),
    )

    assert result.metadata["texturePatterns"] == {"C": "swing"}
    pedal_hats = [hit for hit in result.hits if hit.instrument_class == Instrument.PEDAL_HIHAT]
    assert len(pedal_hats) == 6


def test_completion_recovers_from_a_midtrack_beat_index_slip() -> None:
    hits = [
        *[_detected(Instrument.KICK, index) for index in range(0, 64, 4)],
        *[_detected(Instrument.CLOSED_HIHAT, index) for index in range(0, 64, 4)],
    ]
    slipped = TempoMap(
        (
            TempoChange(0, 120),
            TempoChange(16, 60),
            TempoChange(17, 120),
        ),
        offset_seconds=0.30,
    )

    result = complete_rhythm(
        hits,
        slipped,
        settings=RhythmCompletionSettings(detector_latency_seconds=0.01),
    )

    assert result.applied is True
    assert result.metadata["fitMethod"] in {
        "tracker_indexed",
        "cumulative_kick_grid",
    }
    assert result.tempo_map.changes[0].bpm == pytest.approx(120)
    assert result.tempo_map.offset_seconds == pytest.approx(0.25)


def test_completion_uses_sparse_backbeat_evidence_without_overfilling_hats() -> None:
    hits = [
        *[_detected(Instrument.KICK, index) for index in (*range(0, 64, 4), 13)],
        *[
            _detected(Instrument.CLOSED_HIHAT, index)
            for index in (2, 6, 10, 14, 18, 26, 34, 38, 42, 50, 54, 58)
        ],
        _detected(Instrument.CROSS_STICK, 4),
    ]

    result = complete_rhythm(
        hits,
        TempoMap.constant(120, offset_seconds=0.30),
        settings=RhythmCompletionSettings(detector_latency_seconds=0.01),
    )

    assert result.metadata["texturePatterns"] == {"H": "offbeat"}
    hats = [
        hit
        for hit in result.hits
        if hit.instrument_class
        in {Instrument.CLOSED_HIHAT, Instrument.OPEN_HIHAT, Instrument.PEDAL_HIHAT}
    ]
    snares = [
        hit
        for hit in result.hits
        if hit.instrument_class in {Instrument.SNARE, Instrument.CROSS_STICK}
    ]
    assert len(hats) == 16
    assert len(snares) == 8
    assert {hit.instrument_class for hit in snares} == {Instrument.CROSS_STICK}
