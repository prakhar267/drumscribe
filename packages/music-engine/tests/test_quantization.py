from fractions import Fraction

import pytest

from drumscribe_music import (
    DefaultQuantizer,
    GridSubdivision,
    Instrument,
    RawDrumHit,
    TempoMap,
    deduplicate_raw_hits,
)


def test_quantization_retains_raw_onset_and_assigns_position():
    tempo = TempoMap.constant(120)
    event = DefaultQuantizer().quantize([RawDrumHit("kick", 1.017)], tempo)[0]
    assert event.instrument is Instrument.KICK
    assert event.onset_seconds == 1.017
    assert event.quantized_onset_seconds == pytest.approx(1.0)
    assert event.beat_position == 2
    assert (event.measure_index, event.beat_in_measure) == (0, 2)


def test_near_simultaneous_different_instruments_share_grid_but_not_raw_time():
    hits = [RawDrumHit("kick", 1.0), RawDrumHit("snare", 1.015)]
    events = DefaultQuantizer().quantize(hits, TempoMap.constant(120))
    assert events[0].beat_position == events[1].beat_position == 2
    assert [event.onset_seconds for event in events] == [1.0, 1.015]


def test_triplet_grid_is_selected_when_materially_closer():
    event = DefaultQuantizer().quantize([RawDrumHit("snare", 1 / 6)], TempoMap.constant(120))[0]
    assert event.beat_position == Fraction(1, 3)
    assert event.subdivision is GridSubdivision.EIGHTH_TRIPLET


def test_duplicate_detector_fires_collapse_but_flam_is_preserved_as_grace():
    hits = [
        RawDrumHit("snare", 1.970, confidence=0.7),
        RawDrumHit("snare", 1.974, confidence=0.9),
        RawDrumHit("snare", 2.000, confidence=0.95),
    ]
    deduped = deduplicate_raw_hits(hits)
    assert len(deduped) == 2 and deduped[0].onset_seconds == 1.974
    events = DefaultQuantizer().quantize(hits, TempoMap.constant(120))
    assert len(events) == 2
    assert events[0].is_grace and events[0].grace_of_event_id == events[1].id
    assert events[0].beat_position == events[1].beat_position == 4


def test_same_instrument_hits_are_not_grouped_as_simultaneous():
    events = DefaultQuantizer().quantize(
        [RawDrumHit("kick", 0.49), RawDrumHit("kick", 0.74)], TempoMap.constant(120)
    )
    assert [event.beat_position for event in events] == [1, Fraction(3, 2)]


def test_hits_before_configured_bar_one_keep_raw_time_but_clamp_notation():
    tempo = TempoMap.constant(120, offset_seconds=1.0)
    event = DefaultQuantizer().quantize([RawDrumHit("kick", 0.5)], tempo)[0]
    assert event.onset_seconds == 0.5
    assert event.beat_position == 0
    assert event.quantized_onset_seconds == 1.0
    assert (event.measure_index, event.beat_in_measure) == (0, 0)
