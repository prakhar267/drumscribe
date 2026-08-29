"""MusicXML 4.0 percussion score projection with stable canonical-event IDs."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable
from fractions import Fraction
from pathlib import Path

from ..mapping import INSTRUMENT_TO_GM, NOTATION_PLACEMENT
from ..models import DrumEvent, Instrument
from ..tempo import TempoChange, TempoMap

DIVISIONS = 24

_TYPE_BY_DURATION: dict[Fraction, str] = {
    Fraction(4): "whole",
    Fraction(2): "half",
    Fraction(1): "quarter",
    Fraction(1, 2): "eighth",
    Fraction(1, 4): "16th",
    Fraction(1, 8): "32nd",
}


def generate_musicxml(
    events: Iterable[DrumEvent],
    tempo_map: TempoMap,
    *,
    title: str = "Untitled drum chart",
    artist: str | None = None,
) -> bytes:
    ordered = sorted(
        events, key=lambda event: (event.beat_position or Fraction(0), event.instrument.value)
    )
    root = ET.Element("score-partwise", version="4.0")
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = title
    identification = ET.SubElement(root, "identification")
    if artist:
        ET.SubElement(identification, "creator", type="composer").text = artist
    encoding = ET.SubElement(identification, "encoding")
    ET.SubElement(encoding, "software").text = "DrumScribe music engine"
    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    ET.SubElement(score_part, "part-name").text = "Drum Set"
    ET.SubElement(score_part, "part-abbreviation").text = "Dr."
    for instrument in Instrument:
        instrument_id = _instrument_id(instrument)
        score_instrument = ET.SubElement(score_part, "score-instrument", id=instrument_id)
        ET.SubElement(score_instrument, "instrument-name").text = _instrument_name(instrument)
    for instrument in Instrument:
        instrument_id = _instrument_id(instrument)
        midi_instrument = ET.SubElement(score_part, "midi-instrument", id=instrument_id)
        ET.SubElement(midi_instrument, "midi-channel").text = "10"
        ET.SubElement(midi_instrument, "midi-unpitched").text = str(INSTRUMENT_TO_GM[instrument])

    part = ET.SubElement(root, "part", id="P1")
    grouped: dict[int, dict[Fraction, list[DrumEvent]]] = defaultdict(lambda: defaultdict(list))
    last_beat = Fraction(0)
    xml_ids = [_xml_event_id(event.id) for event in ordered]
    if len(xml_ids) != len(set(xml_ids)):
        raise ValueError("event IDs must be unique after MusicXML ID normalization")
    for event in ordered:
        beat = event.beat_position
        if beat is None:
            beat = tempo_map.seconds_to_beat(event.notation_onset_seconds)
        beat = max(Fraction(0), beat)
        position = tempo_map.beat_to_position(beat)
        grouped[position.measure_index][position.beat_in_measure].append(event)
        last_beat = max(last_beat, beat)
    last_measure = tempo_map.beat_to_position(last_beat).measure_index
    tempo_by_measure: dict[int, list[TempoChange]] = defaultdict(list)
    for change in tempo_map.changes:
        tempo_by_measure[tempo_map.beat_to_position(change.start_beat).measure_index].append(change)

    previous_signature = None
    for measure_index in range(last_measure + 1):
        measure = ET.SubElement(part, "measure", number=str(measure_index + 1))
        measure_start = tempo_map.position_to_beat(measure_index)
        signature = tempo_map.signature_at_beat(measure_start)
        if measure_index == 0 or signature != previous_signature:
            attributes = ET.SubElement(measure, "attributes")
            ET.SubElement(attributes, "divisions").text = str(DIVISIONS)
            key = ET.SubElement(attributes, "key")
            ET.SubElement(key, "fifths").text = "0"
            time = ET.SubElement(attributes, "time")
            ET.SubElement(time, "beats").text = str(signature.numerator)
            ET.SubElement(time, "beat-type").text = str(signature.denominator)
            clef = ET.SubElement(attributes, "clef")
            ET.SubElement(clef, "sign").text = "percussion"
            ET.SubElement(clef, "line").text = "2"
        previous_signature = signature
        for change in tempo_by_measure.get(measure_index, []):
            direction = ET.SubElement(measure, "direction", placement="above")
            direction_type = ET.SubElement(direction, "direction-type")
            metronome = ET.SubElement(direction_type, "metronome")
            ET.SubElement(metronome, "beat-unit").text = "quarter"
            ET.SubElement(metronome, "per-minute").text = f"{change.bpm:g}"
            offset = change.start_beat - measure_start
            if offset > 0:
                ET.SubElement(direction, "offset", sound="yes").text = str(
                    round(float(offset * DIVISIONS))
                )
            ET.SubElement(direction, "sound", tempo=f"{change.bpm:g}")
        measure_length = signature.quarter_note_beats_per_measure
        points = sorted(grouped.get(measure_index, {}))
        cursor = Fraction(0)
        for point_index, beat_in_measure in enumerate(points):
            if beat_in_measure > cursor:
                _append_rest(measure, beat_in_measure - cursor)
            next_beat = points[point_index + 1] if point_index + 1 < len(points) else measure_length
            duration = min(Fraction(1), max(Fraction(1, 8), next_beat - beat_in_measure))
            chord = grouped[measure_index][beat_in_measure]
            sounding_index = 0
            for event in sorted(chord, key=lambda item: not item.is_grace):
                _append_note(
                    measure,
                    event,
                    duration,
                    chord=not event.is_grace and sounding_index > 0,
                )
                if not event.is_grace:
                    sounding_index += 1
            cursor = beat_in_measure + duration
        if cursor < measure_length:
            _append_rest(measure, measure_length - cursor)
        if measure_index == last_measure:
            barline = ET.SubElement(measure, "barline", location="right")
            ET.SubElement(barline, "bar-style").text = "light-heavy"

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_musicxml(
    destination: str | os.PathLike[str],
    events: Iterable[DrumEvent],
    tempo_map: TempoMap,
    *,
    title: str = "Untitled drum chart",
    artist: str | None = None,
    overwrite: bool = False,
) -> Path:
    path = Path(destination).expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if overwrite else "xb"
    with path.open(mode) as handle:
        handle.write(generate_musicxml(events, tempo_map, title=title, artist=artist))
    return path


def _append_rest(measure: ET.Element, duration: Fraction) -> None:
    ticks = _duration_ticks(duration)
    if ticks <= 0:
        return
    note = ET.SubElement(measure, "note")
    ET.SubElement(note, "rest")
    ET.SubElement(note, "duration").text = str(ticks)
    ET.SubElement(note, "voice").text = "1"
    note_type = _duration_type(duration)
    if note_type:
        ET.SubElement(note, "type").text = note_type


def _append_note(measure: ET.Element, event: DrumEvent, duration: Fraction, chord: bool) -> None:
    note = ET.SubElement(measure, "note", id=_xml_event_id(event.id))
    if chord:
        ET.SubElement(note, "chord")
    if event.is_grace:
        ET.SubElement(note, "grace", slash="yes")
    placement = NOTATION_PLACEMENT[event.instrument]
    unpitched = ET.SubElement(note, "unpitched")
    ET.SubElement(unpitched, "display-step").text = placement.display_step
    ET.SubElement(unpitched, "display-octave").text = str(placement.display_octave)
    ET.SubElement(note, "instrument", id=_instrument_id(event.instrument))
    if not event.is_grace:
        ET.SubElement(note, "duration").text = str(_duration_ticks(duration))
    ET.SubElement(note, "voice").text = "1"
    note_type = _duration_type(duration)
    if note_type:
        ET.SubElement(note, "type").text = note_type
    ET.SubElement(note, "stem").text = placement.stem
    ET.SubElement(note, "notehead").text = placement.notehead
    if duration.denominator in (3, 6, 12):
        time_modification = ET.SubElement(note, "time-modification")
        ET.SubElement(time_modification, "actual-notes").text = "3"
        ET.SubElement(time_modification, "normal-notes").text = "2"
    if event.instrument is Instrument.OPEN_HIHAT:
        notations = ET.SubElement(note, "notations")
        ET.SubElement(notations, "other-notation", type="single").text = "open hi-hat"


def _duration_ticks(duration: Fraction) -> int:
    ticks = duration * DIVISIONS
    if ticks.denominator != 1:
        raise ValueError(f"duration {duration} cannot be represented at {DIVISIONS} divisions")
    return ticks.numerator


def _duration_type(duration: Fraction) -> str | None:
    if duration in _TYPE_BY_DURATION:
        return _TYPE_BY_DURATION[duration]
    # Triplets carry a normal note type plus time-modification.
    return {Fraction(1, 3): "eighth", Fraction(1, 6): "16th"}.get(duration)


def _xml_event_id(value: str) -> str:
    return "event-" + re.sub(r"[^A-Za-z0-9_.-]", "-", value)


def _instrument_id(instrument: Instrument) -> str:
    return f"P1-I{INSTRUMENT_TO_GM[instrument]}"


def _instrument_name(instrument: Instrument) -> str:
    return instrument.value.replace("_", " ").title()
