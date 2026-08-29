from fractions import Fraction

import pytest

from drumscribe_music import TempoChange, TempoMap, TimeSignature


def test_constant_tempo_round_trip_is_precise():
    tempo = TempoMap.constant(120, offset_seconds=0.25)
    assert tempo.beat_to_seconds(Fraction(7, 3)) == pytest.approx(1.4166666667)
    assert float(tempo.seconds_to_beat(1.4166666667)) == pytest.approx(7 / 3, abs=1e-8)


def test_piecewise_tempo_conversion_and_boundary_round_trip():
    tempo = TempoMap((TempoChange(0, 120), TempoChange(4, 60), TempoChange(8, 180)))
    assert tempo.beat_to_seconds(4) == pytest.approx(2)
    assert tempo.beat_to_seconds(6) == pytest.approx(4)
    assert tempo.beat_to_seconds(11) == pytest.approx(7)
    for beat in (0, Fraction(1, 3), 4, Fraction(13, 2), 8, Fraction(35, 3)):
        assert float(tempo.seconds_to_beat(tempo.beat_to_seconds(beat))) == pytest.approx(
            float(beat)
        )


def test_time_signature_positions_across_change():
    tempo = TempoMap(
        (TempoChange(0, 100),),
        (TimeSignature(4, 4, 0), TimeSignature(3, 4, 8)),
    )
    before = tempo.beat_to_position(Fraction(7, 2))
    assert (before.measure_index, before.beat_in_measure) == (0, Fraction(7, 2))
    change = tempo.beat_to_position(8)
    assert (change.measure_index, change.beat_in_measure) == (2, 0)
    after = tempo.beat_to_position(14)
    assert (after.measure_index, after.beat_in_measure) == (4, 0)
    assert tempo.position_to_beat(4) == 14


def test_invalid_maps_are_rejected():
    with pytest.raises(ValueError, match="beat 0"):
        TempoMap((TempoChange(1, 120),))
    with pytest.raises(ValueError, match="unique"):
        TempoMap((TempoChange(0, 120), TempoChange(0, 100)))
    with pytest.raises(ValueError, match="power of two"):
        TimeSignature(4, 3)


def test_nearest_grid_includes_triplets():
    tempo = TempoMap.constant(120)
    beat, step, seconds = tempo.nearest_grid(1 / 6, [Fraction(1, 4), Fraction(1, 3)])
    assert beat == Fraction(1, 3)
    assert step == Fraction(1, 3)
    assert seconds == pytest.approx(1 / 6)
