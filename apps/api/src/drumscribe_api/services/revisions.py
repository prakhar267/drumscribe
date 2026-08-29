import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import EventSource, Instrument, RevisionKind
from ..errors import APIError
from ..models import DrumEvent, Transcription, TranscriptionRevision

EVENT_SNAPSHOT_FIELDS = (
    "id",
    "instrument",
    "onset_seconds",
    "duration_seconds",
    "velocity",
    "confidence",
    "source",
    "beat_position",
    "measure_index",
    "subdivision",
    "quantized_onset",
    "manually_edited",
)


def event_snapshot(event: DrumEvent) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in EVENT_SNAPSHOT_FIELDS:
        value = getattr(event, field)
        if isinstance(value, (Instrument, EventSource)):
            value = value.value
        elif isinstance(value, uuid.UUID):
            value = str(value)
        result[field] = value
    return result


async def current_snapshot(db: AsyncSession, transcription_id: uuid.UUID) -> list[dict[str, Any]]:
    events = (
        await db.execute(
            select(DrumEvent)
            .where(
                DrumEvent.transcription_id == transcription_id,
                DrumEvent.deleted_at.is_(None),
            )
            .order_by(DrumEvent.quantized_onset, DrumEvent.instrument, DrumEvent.id)
        )
    ).scalars()
    return [event_snapshot(event) for event in events]


async def create_revision(
    db: AsyncSession,
    transcription: Transcription,
    *,
    kind: RevisionKind,
    label: str,
    created_by_user_id: uuid.UUID | None,
    snapshot: list[dict[str, Any]] | None = None,
) -> TranscriptionRevision:
    next_sequence = (
        await db.scalar(
            select(func.coalesce(func.max(TranscriptionRevision.sequence), 0) + 1).where(
                TranscriptionRevision.transcription_id == transcription.id
            )
        )
        or 1
    )
    revision = TranscriptionRevision(
        transcription_id=transcription.id,
        project_id=transcription.project_id,
        sequence=int(next_sequence),
        kind=kind,
        label=label,
        snapshot=snapshot if snapshot is not None else await current_snapshot(db, transcription.id),
        created_by_user_id=created_by_user_id,
    )
    db.add(revision)
    await db.flush()
    return revision


async def restore_snapshot(
    db: AsyncSession,
    transcription: Transcription,
    revision: TranscriptionRevision,
) -> int:
    existing = {
        event.id: event
        for event in (
            await db.execute(
                select(DrumEvent).where(DrumEvent.transcription_id == transcription.id)
            )
        ).scalars()
    }
    restored_ids: set[uuid.UUID] = set()
    for payload in revision.snapshot:
        try:
            event_id = uuid.UUID(str(payload["id"]))
            instrument = Instrument(str(payload["instrument"]))
            source = EventSource(str(payload["source"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise APIError(
                409,
                "REVISION_CORRUPT",
                "This revision cannot be restored because its snapshot is invalid.",
            ) from exc
        restored_ids.add(event_id)
        event = existing.get(event_id)
        if event is None:
            event = DrumEvent(
                id=event_id,
                transcription_id=transcription.id,
                project_id=transcription.project_id,
                instrument=instrument,
                onset_seconds=float(payload["onset_seconds"]),
                duration_seconds=float(payload["duration_seconds"]),
                velocity=int(payload["velocity"]),
                confidence=(
                    float(payload["confidence"]) if payload.get("confidence") is not None else None
                ),
                source=source,
                beat_position=float(payload["beat_position"]),
                measure_index=int(payload["measure_index"]),
                subdivision=str(payload["subdivision"]),
                quantized_onset=float(payload["quantized_onset"]),
                manually_edited=bool(payload.get("manually_edited", False)),
            )
            db.add(event)
        else:
            event.instrument = instrument
            event.onset_seconds = float(payload["onset_seconds"])
            event.duration_seconds = float(payload["duration_seconds"])
            event.velocity = int(payload["velocity"])
            event.confidence = (
                float(payload["confidence"]) if payload.get("confidence") is not None else None
            )
            event.source = source
            event.beat_position = float(payload["beat_position"])
            event.measure_index = int(payload["measure_index"])
            event.subdivision = str(payload["subdivision"])
            event.quantized_onset = float(payload["quantized_onset"])
            event.manually_edited = bool(payload.get("manually_edited", False))
            event.deleted_at = None
    from ..security import utcnow

    for event_id, event in existing.items():
        if event_id not in restored_ids and event.deleted_at is None:
            event.deleted_at = utcnow()
    transcription.version += 1
    return len(restored_ids)

