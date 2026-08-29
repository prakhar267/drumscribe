from fractions import Fraction

import pytest

from drumscribe_music import (
    GM_PERCUSSION_CHANNEL,
    INSTRUMENT_TO_GM,
    DrumEvent,
    GridSubdivision,
    Instrument,
    RawDrumHit,
    canonical_instrument,
    gm_note,
)


def test_complete_initial_instrument_taxonomy_and_unique_primary_gm_notes():
    assert {item.value for item in Instrument} == {
        "KICK",
        "SNARE",
        "CROSS_STICK",
        "CLOSED_HIHAT",
        "OPEN_HIHAT",
        "PEDAL_HIHAT",
        "RIDE",
        "RIDE_BELL",
        "CRASH",
        "HIGH_TOM",
        "MID_TOM",
        "LOW_TOM",
        "FLOOR_TOM",
    }
    assert len(set(INSTRUMENT_TO_GM.values())) == len(Instrument)
    assert GM_PERCUSSION_CHANNEL == 9
    assert gm_note(Instrument.KICK) == 36


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Bass Drum", Instrument.KICK),
        ("OH-H", Instrument.OPEN_HIHAT),
        ("ride cymbal", Instrument.RIDE),
        (37, Instrument.CROSS_STICK),
        (43, Instrument.FLOOR_TOM),
        ("53", Instrument.RIDE_BELL),
    ],
)
def test_raw_and_gm_mapping(raw, expected):
    assert canonical_instrument(raw) is expected


def test_unknown_mapping_is_fail_closed():
    with pytest.raises(ValueError, match="unknown drum"):
        canonical_instrument("laser gong")


def test_raw_hit_and_event_validation():
    with pytest.raises(ValueError, match="velocity"):
        RawDrumHit("kick", 0.1, velocity=0)
    with pytest.raises(ValueError, match="confidence"):
        RawDrumHit("kick", 0.1, confidence=1.1)
    event = DrumEvent(
        id="event-one",
        instrument=Instrument.SNARE,
        onset_seconds=1.037,
        beat_position=Fraction(2),
        measure_index=0,
        beat_in_measure=Fraction(2),
        subdivision=GridSubdivision.QUARTER,
        quantized_onset_seconds=1.0,
    )
    assert event.playback_onset_seconds == 1.037
    assert event.notation_onset_seconds == 1.0
    assert event.as_dict()["beatPosition"] == "2"
    edited = event.edited(velocity=80)
    assert edited.manually_edited and edited.velocity == 80 and event.velocity == 100


def test_event_normalizes_numeric_beat_positions_and_rejects_negative_notation():
    event = DrumEvent(
        instrument=Instrument.KICK,
        onset_seconds=0,
        beat_position=1.5,
        beat_in_measure=0.5,
    )
    assert event.beat_position == Fraction(3, 2)
    assert event.as_dict()["beatInMeasure"] == "1/2"
    with pytest.raises(ValueError, match="beat_position"):
        DrumEvent(instrument=Instrument.KICK, onset_seconds=0, beat_position=-1)
