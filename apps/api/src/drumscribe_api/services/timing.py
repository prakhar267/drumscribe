"""Canonical timing-map editing and selective event requantization."""

from __future__ import annotations

import bisect
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import RevisionKind
from ..errors import APIError
from ..models import DrumEvent, Project, Transcription
from ..schemas import BeatWrite, TempoSegmentWrite, TimingResponse
from .revisions import create_revision, current_snapshot


@dataclass(frozen=True, slots=True)
class TimingState:
    bar_one_seconds: float
    segments: tuple[TempoSegmentWrite, ...]
    beats: tuple[BeatWrite, ...]
    source: Literal["AI", "MANUAL"]


def _number(item: dict[str, Any], key: str, default: float) -> float:
    value = item.get(key)
    return float(value) if isinstance(value, int | float) else default


def _integer(item: dict[str, Any], key: str, default: int) -> int:
    value = item.get(key)
    return int(value) if isinstance(value, int | float) else default


def parse_timing(
    transcription: Transcription,
    duration_seconds: float,
    payload_override: list[dict[str, Any]] | None = None,
) -> TimingState:
    payload = payload_override if payload_override is not None else transcription.tempo_map or []
    offset = 0.0
    source: Literal["AI", "MANUAL"] = "AI"
    tempo_rows: list[dict[str, Any]] = []
    signature_rows: list[dict[str, Any]] = []
    beat_rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        if kind == "offset":
            offset = max(0.0, _number(item, "offsetSeconds", 0))
        elif kind == "timingSource" and item.get("source") == "MANUAL":
            source = "MANUAL"
        elif kind == "tempo":
            tempo_rows.append(item)
        elif kind == "timeSignature":
            signature_rows.append(item)
        elif kind == "beat":
            beat_rows.append(item)

    segments: list[TempoSegmentWrite] = []
    if not tempo_rows:
        tempo_rows = [
            {
                "startSeconds": offset,
                "startMeasure": 0,
                "bpm": transcription.tempo_bpm,
            }
        ]
    for index, tempo in enumerate(tempo_rows):
        start_measure = _integer(tempo, "startMeasure", index)
        start_seconds = _number(
            tempo,
            "startSeconds",
            offset + _number(tempo, "startBeat", 0) * 60 / transcription.tempo_bpm,
        )
        signature = next(
            (
                item
                for item in signature_rows
                if _integer(item, "startMeasure", start_measure) == start_measure
            ),
            signature_rows[min(index, len(signature_rows) - 1)] if signature_rows else {},
        )
        segments.append(
            TempoSegmentWrite(
                start_seconds=max(0, start_seconds),
                bpm=_number(tempo, "bpm", transcription.tempo_bpm),
                time_signature_numerator=_integer(
                    signature, "numerator", transcription.time_signature_numerator
                ),
                time_signature_denominator=_integer(
                    signature, "denominator", transcription.time_signature_denominator
                ),
                start_measure=max(0, start_measure),
            )
        )
    segments.sort(key=lambda item: item.start_seconds)

    beats = tuple(_parse_beat(item) for item in beat_rows)
    if not beats:
        beats = generate_beats(tuple(segments), duration_seconds)
    downbeats = [beat for beat in beats if beat.is_downbeat]
    bar_one = downbeats[0].time_seconds if downbeats else offset
    return TimingState(bar_one, tuple(segments), beats, source)


def _parse_beat(item: dict[str, Any]) -> BeatWrite:
    return BeatWrite(
        time_seconds=max(0, _number(item, "timeSeconds", 0)),
        beat_in_measure=max(1, _integer(item, "beatInMeasure", 1)),
        measure_index=max(0, _integer(item, "measureIndex", 0)),
        is_downbeat=bool(item.get("isDownbeat")),
        confidence=(
            max(0, min(1, _number(item, "confidence", 0.5)))
            if item.get("confidence") is not None
            else None
        ),
    )


def generate_beats(
    segments: tuple[TempoSegmentWrite, ...], duration_seconds: float
) -> tuple[BeatWrite, ...]:
    output: list[BeatWrite] = []
    for index, segment in enumerate(segments):
        end = (
            segments[index + 1].start_seconds
            if index + 1 < len(segments)
            else max(duration_seconds, segment.start_seconds + 0.001)
        )
        beat_duration = 60 / segment.bpm * 4 / segment.time_signature_denominator
        timestamp = segment.start_seconds
        beat_index = 0
        while timestamp <= end + 1e-9 and len(output) < 50_000:
            beat_in_measure = beat_index % segment.time_signature_numerator + 1
            measure_index = segment.start_measure + beat_index // segment.time_signature_numerator
            if not output or abs(output[-1].time_seconds - timestamp) > 1e-7:
                output.append(
                    BeatWrite(
                        time_seconds=round(timestamp, 9),
                        beat_in_measure=beat_in_measure,
                        measure_index=measure_index,
                        is_downbeat=beat_in_measure == 1,
                        confidence=None,
                    )
                )
            beat_index += 1
            timestamp = segment.start_seconds + beat_index * beat_duration
    if len(output) < 2:
        raise APIError(422, "TIMING_GRID_TOO_SHORT", "The timing grid needs at least two beats.")
    return tuple(output)


def serialize_timing(state: TimingState) -> list[dict[str, Any]]:
    return [
        *[
            {
                "kind": "tempo",
                "startSeconds": item.start_seconds,
                "bpm": item.bpm,
                "startMeasure": item.start_measure,
                "confidence": None,
            }
            for item in state.segments
        ],
        *[
            {
                "kind": "timeSignature",
                "startSeconds": item.start_seconds,
                "startMeasure": item.start_measure,
                "numerator": item.time_signature_numerator,
                "denominator": item.time_signature_denominator,
                "confidence": None,
            }
            for item in state.segments
        ],
        *[
            {
                "kind": "beat",
                "timeSeconds": item.time_seconds,
                "beatInMeasure": item.beat_in_measure,
                "measureIndex": item.measure_index,
                "isDownbeat": item.is_downbeat,
                "confidence": item.confidence,
            }
            for item in state.beats
        ],
        {"kind": "offset", "offsetSeconds": state.bar_one_seconds},
        {"kind": "timingSource", "source": state.source},
    ]


def response_for(
    transcription: Transcription,
    state: TimingState,
    *,
    requantized_event_count: int = 0,
    revision_id: uuid.UUID | None = None,
) -> TimingResponse:
    return TimingResponse(
        timing_version=transcription.timing_version,
        transcription_version=transcription.version,
        bar_one_seconds=state.bar_one_seconds,
        segments=list(state.segments),
        beats=list(state.beats),
        source=state.source,
        requantized_event_count=requantized_event_count,
        revision_id=revision_id,
    )


async def apply_timing(
    db: AsyncSession,
    *,
    project: Project,
    transcription: Transcription,
    state: TimingState,
    expected_version: int,
    requantize: Literal["none", "all", "selected"],
    measure_start: int | None,
    measure_end: int | None,
    preserve_manual_edits: bool,
    user_id: uuid.UUID,
    revision_label: str,
) -> tuple[int, uuid.UUID]:
    locked = (
        await db.execute(
            select(Transcription).where(Transcription.id == transcription.id).with_for_update()
        )
    ).scalar_one()
    if locked.timing_version != expected_version:
        raise APIError(
            409,
            "TIMING_VERSION_CONFLICT",
            "The timing map changed on another client. Reload before saving timing.",
        )
    if not locked.timing_ai_baseline:
        locked.timing_ai_baseline = list(locked.tempo_map or [])
    locked.tempo_map = serialize_timing(state)
    first_segment = state.segments[0]
    locked.tempo_bpm = first_segment.bpm
    locked.time_signature_numerator = first_segment.time_signature_numerator
    locked.time_signature_denominator = first_segment.time_signature_denominator
    requantized = await _requantize_events(
        db,
        transcription=locked,
        state=state,
        mode=requantize,
        measure_start=measure_start,
        measure_end=measure_end,
        preserve_manual_edits=preserve_manual_edits,
    )
    locked.timing_version += 1
    locked.version += 1
    project.edit_version = locked.version
    await db.flush()
    revision = await create_revision(
        db,
        locked,
        kind=RevisionKind.MANUAL,
        label=revision_label,
        created_by_user_id=user_id,
        snapshot=await current_snapshot(db, locked.id),
    )
    return requantized, revision.id


async def _requantize_events(
    db: AsyncSession,
    *,
    transcription: Transcription,
    state: TimingState,
    mode: Literal["none", "all", "selected"],
    measure_start: int | None,
    measure_end: int | None,
    preserve_manual_edits: bool,
) -> int:
    if mode == "none":
        return 0
    candidates = _grid_candidates(state)
    candidate_times = [item[0] for item in candidates]
    events = list(
        (
            await db.execute(
                select(DrumEvent).where(
                    DrumEvent.transcription_id == transcription.id,
                    DrumEvent.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    count = 0
    for event in events:
        if preserve_manual_edits and event.manually_edited:
            continue
        if mode == "selected" and (
            measure_start is None
            or measure_end is None
            or not measure_start <= event.measure_index <= measure_end
        ):
            continue
        index = bisect.bisect_left(candidate_times, event.onset_seconds)
        choices = candidates[max(0, index - 1) : min(len(candidates), index + 1)]
        if not choices:
            continue
        timestamp, measure, beat_position, subdivision = min(
            choices, key=lambda item: abs(item[0] - event.onset_seconds)
        )
        event.quantized_onset = timestamp
        event.measure_index = measure
        event.beat_position = beat_position
        event.subdivision = subdivision
        count += 1
    return count


def _grid_candidates(
    state: TimingState,
) -> list[tuple[float, int, float, str]]:
    candidates: list[tuple[float, int, float, str]] = []
    for index, beat in enumerate(state.beats):
        segment = max(
            (item for item in state.segments if item.start_seconds <= beat.time_seconds),
            key=lambda item: item.start_seconds,
            default=state.segments[0],
        )
        divisions = 2 if segment.time_signature_denominator >= 8 else 4
        next_time = (
            state.beats[index + 1].time_seconds
            if index + 1 < len(state.beats)
            else beat.time_seconds + 60 / segment.bpm * 4 / segment.time_signature_denominator
        )
        interval = max(1e-6, next_time - beat.time_seconds)
        for division in range(divisions):
            candidates.append(
                (
                    beat.time_seconds + interval * division / divisions,
                    beat.measure_index,
                    beat.beat_in_measure - 1 + division / divisions,
                    "1/16",
                )
            )
    return candidates
