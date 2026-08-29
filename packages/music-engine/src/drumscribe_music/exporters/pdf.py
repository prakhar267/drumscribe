"""Readable vector PDF chart with no mandatory third-party dependency."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Iterable
from fractions import Fraction
from pathlib import Path

from ..mapping import NOTATION_PLACEMENT
from ..models import DrumEvent
from ..tempo import TempoMap

PAGE_WIDTH = 612
PAGE_HEIGHT = 792


def generate_pdf(
    events: Iterable[DrumEvent],
    tempo_map: TempoMap,
    *,
    title: str = "Untitled drum chart",
    artist: str | None = None,
) -> bytes:
    """Render a compact staff-oriented chart with titles, tempo, signatures, and pages."""

    ordered = sorted(
        events, key=lambda event: (event.beat_position or Fraction(0), event.instrument.value)
    )
    grouped: dict[int, list[tuple[Fraction, DrumEvent]]] = defaultdict(list)
    last_measure = 0
    for event in ordered:
        beat = event.beat_position
        if beat is None:
            beat = tempo_map.seconds_to_beat(event.notation_onset_seconds)
        position = tempo_map.beat_to_position(max(Fraction(0), beat))
        grouped[position.measure_index].append((position.beat_in_measure, event))
        last_measure = max(last_measure, position.measure_index)
    measure_count = last_measure + 1
    measures_per_page = 12
    page_streams: list[bytes] = []
    for page_start in range(0, measure_count, measures_per_page):
        commands: list[str] = []
        _text(commands, 54, 744, 18, title)
        subtitle = ""
        if artist:
            subtitle += artist + "  |  "
        first_tempo = tempo_map.changes[0].bpm
        first_signature = tempo_map.time_signatures[0]
        subtitle += (
            f"quarter = {first_tempo:g}   {first_signature.numerator}/{first_signature.denominator}"
        )
        _text(commands, 54, 722, 10, subtitle)
        for local_index in range(measures_per_page):
            measure_index = page_start + local_index
            if measure_index >= measure_count:
                break
            row = local_index // 3
            column = local_index % 3
            x = 54 + column * 168
            y = 670 - row * 145
            width = 150
            _text(commands, x, y + 18, 8, str(measure_index + 1))
            for staff_line in range(5):
                line_y = y + staff_line * 8
                commands.append(f"0.5 w {x} {line_y} m {x + width} {line_y} l S")
            commands.append(f"0.8 w {x} {y} m {x} {y + 32} l S")
            commands.append(f"0.8 w {x + width} {y} m {x + width} {y + 32} l S")
            signature = tempo_map.signature_at_beat(tempo_map.position_to_beat(measure_index))
            measure_beats = float(signature.quarter_note_beats_per_measure)
            for beat_in_measure, event in grouped.get(measure_index, []):
                event_x = x + 8 + (width - 16) * float(beat_in_measure) / measure_beats
                event_y = _staff_y(y, event)
                glyph = "x" if NOTATION_PLACEMENT[event.instrument].notehead == "x" else "o"
                _text(commands, event_x - 2, event_y - 3, 8, glyph)
                commands.append(f"0.5 w {event_x + 3} {event_y} m {event_x + 3} {event_y + 20} l S")
        page_number = len(page_streams) + 1
        _text(commands, PAGE_WIDTH / 2 - 12, 28, 9, f"Page {page_number}")
        page_streams.append("\n".join(commands).encode("ascii", "replace"))
    return _assemble_pdf(page_streams)


def write_pdf(
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
        handle.write(generate_pdf(events, tempo_map, title=title, artist=artist))
    return path


def _staff_y(base: float, event: DrumEvent) -> float:
    placement = NOTATION_PLACEMENT[event.instrument]
    diatonic = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
    absolute = placement.display_octave * 7 + diatonic[placement.display_step]
    reference = 4 * 7 + diatonic["E"]
    return base + 16 + (absolute - reference) * 4


def _text(commands: list[str], x: float, y: float, size: int, value: str) -> None:
    escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    commands.append(f"BT /F1 {size} Tf {x:g} {y:g} Td ({escaped}) Tj ET")


def _assemble_pdf(streams: list[bytes]) -> bytes:
    page_count = len(streams)
    font_id = 3 + page_count * 2
    kids = " ".join(f"{3 + index * 2} 0 R" for index in range(page_count))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode(),
    ]
    for index, stream in enumerate(streams):
        content_id = 4 + index * 2
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, payload in enumerate(objects, 1):
        offsets.append(len(document))
        document.extend(f"{object_id} 0 obj\n".encode())
        document.extend(payload)
        document.extend(b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(document)
