import struct
import xml.etree.ElementTree as ET
from fractions import Fraction

import pytest

from drumscribe_music import (
    DrumEvent,
    GridSubdivision,
    Instrument,
    TempoChange,
    TempoMap,
    generate_midi,
    generate_musicxml,
    generate_pdf,
)


def _events():
    tempo = TempoMap.constant(120)
    values = [
        ("kick-0", Instrument.KICK, Fraction(0)),
        ("hat-0", Instrument.CLOSED_HIHAT, Fraction(0)),
        ("snare-1", Instrument.SNARE, Fraction(1)),
        ("hat-triplet", Instrument.OPEN_HIHAT, Fraction(4, 3)),
        ("ride-2", Instrument.RIDE, Fraction(2)),
    ]
    events = []
    for event_id, instrument, beat in values:
        position = tempo.beat_to_position(beat)
        events.append(
            DrumEvent(
                id=event_id,
                instrument=instrument,
                onset_seconds=tempo.beat_to_seconds(beat),
                beat_position=beat,
                measure_index=position.measure_index,
                beat_in_measure=position.beat_in_measure,
                subdivision=GridSubdivision.EIGHTH_TRIPLET,
                quantized_onset_seconds=tempo.beat_to_seconds(beat),
            )
        )
    return tempo, events


def test_musicxml_has_percussion_metadata_stable_ids_and_gm_channel_10():
    tempo, events = _events()
    payload = generate_musicxml(events, tempo, title="Fixture", artist="Generated")
    root = ET.fromstring(payload)
    assert root.tag == "score-partwise" and root.attrib["version"] == "4.0"
    assert root.findtext("./work/work-title") == "Fixture"
    assert len(root.findall("./part-list/score-part/score-instrument")) == len(Instrument)
    assert {node.text for node in root.findall(".//midi-channel")} == {"10"}
    score_part_children = [node.tag for node in root.findall("./part-list/score-part/*")]
    assert score_part_children.index("midi-instrument") > max(
        index for index, tag in enumerate(score_part_children) if tag == "score-instrument"
    )
    note_ids = {note.attrib["id"] for note in root.findall(".//note[@id]")}
    assert "event-kick-0" in note_ids and "event-hat-triplet" in note_ids
    assert root.find(".//clef/sign").text == "percussion"
    assert root.find(".//notehead[.='x']") is not None


def test_musicxml_places_mid_measure_tempo_changes_at_an_offset():
    _, events = _events()
    tempo = TempoMap((TempoChange(0, 120), TempoChange(2, 90)))
    root = ET.fromstring(generate_musicxml(events, tempo))
    directions = root.findall(".//direction")
    assert len(directions) == 2
    assert directions[1].findtext("offset") == "48"


def test_musicxml_rejects_event_id_collisions_that_would_make_invalid_xml():
    tempo = TempoMap.constant()
    first = DrumEvent(id="a:b", instrument=Instrument.KICK, onset_seconds=0)
    second = DrumEvent(id="a?b", instrument=Instrument.SNARE, onset_seconds=0)
    with pytest.raises(ValueError, match="unique"):
        generate_musicxml([first, second], tempo)


def test_midi_is_format_one_with_conductor_and_channel_10_percussion():
    tempo, events = _events()
    payload = generate_midi(events, tempo)
    assert payload[:4] == b"MThd"
    length, midi_format, tracks, resolution = struct.unpack(">IHHH", payload[4:14])
    assert (length, midi_format, tracks, resolution) == (6, 1, 2, 480)
    assert payload.count(b"MTrk") == 2
    assert bytes((0x99, 36, 100)) in payload  # channel 10, GM bass drum 1
    assert b"\xff\x51\x03" in payload and b"\xff\x58\x04" in payload


def test_pdf_is_valid_vector_document_with_metadata_and_page_number():
    tempo, events = _events()
    payload = generate_pdf(events, tempo, title="Fixture Chart", artist="Generated")
    assert payload.startswith(b"%PDF-1.4") and payload.rstrip().endswith(b"%%EOF")
    assert b"Fixture Chart" in payload and b"Generated" in payload and b"Page 1" in payload
    assert b"xref" in payload and b"/Type /Page" in payload
