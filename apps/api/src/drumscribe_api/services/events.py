import uuid
from dataclasses import dataclass
from math import isclose

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import EventSource, RevisionKind
from ..errors import APIError, not_found
from ..models import DrumEvent, Project, Transcription
from ..schemas import BulkEventsRequest
from ..security import utcnow
from .revisions import create_revision, current_snapshot


@dataclass(slots=True)
class CorrectionBurden:
    events_added: int = 0
    events_deleted: int = 0
    events_moved: int = 0
    instruments_reassigned: int = 0
    velocities_changed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "eventsAdded": self.events_added,
            "eventsDeleted": self.events_deleted,
            "eventsMoved": self.events_moved,
            "instrumentsReassigned": self.instruments_reassigned,
            "velocitiesChanged": self.velocities_changed,
        }


async def apply_bulk_events(
    db: AsyncSession,
    *,
    project: Project,
    transcription: Transcription,
    payload: BulkEventsRequest,
    user_id: uuid.UUID,
    max_events: int,
) -> tuple[list[DrumEvent], list[uuid.UUID], uuid.UUID | None, CorrectionBurden]:
    operation_count = len(payload.upserts) + len(payload.delete_ids)
    if operation_count == 0:
        raise APIError(422, "EMPTY_EDIT_BATCH", "Submit at least one event change.")
    if operation_count > max_events:
        raise APIError(
            413,
            "EDIT_BATCH_TOO_LARGE",
            f"A single edit batch may contain at most {max_events} changes.",
        )
    locked_transcription = (
        await db.execute(
            select(Transcription).where(Transcription.id == transcription.id).with_for_update()
        )
    ).scalar_one()
    transcription = locked_transcription
    if payload.expected_version != transcription.version:
        raise APIError(
            409,
            "EDIT_VERSION_CONFLICT",
            "The chart changed on another client. Reload before applying this edit batch.",
        )

    requested_ids = {item.id for item in payload.upserts if item.id is not None} | set(
        payload.delete_ids
    )
    existing: dict[uuid.UUID, DrumEvent] = {}
    if requested_ids:
        existing = {
            event.id: event
            for event in (
                await db.execute(select(DrumEvent).where(DrumEvent.id.in_(requested_ids)))
            ).scalars()
        }
        invalid = [
            event_id
            for event_id, event in existing.items()
            if event.transcription_id != transcription.id or event.project_id != project.id
        ]
        if invalid:
            raise not_found("Drum event")

    upserted: list[DrumEvent] = []
    burden = CorrectionBurden()
    for write in payload.upserts:
        event = existing.get(write.id) if write.id else None
        if event is None:
            if write.id is not None and write.id in requested_ids and write.id in existing:
                raise not_found("Drum event")
            event = DrumEvent(
                id=write.id or uuid.uuid4(),
                transcription_id=transcription.id,
                project_id=project.id,
                instrument=write.instrument,
                onset_seconds=write.onset_seconds,
                duration_seconds=write.duration_seconds,
                velocity=write.velocity,
                confidence=write.confidence,
                source=EventSource.USER,
                beat_position=write.beat_position,
                measure_index=write.measure_index,
                subdivision=write.subdivision,
                quantized_onset=write.quantized_onset,
                manually_edited=True,
            )
            db.add(event)
            burden.events_added += 1
        else:
            confidence_changed = (
                "confidence" in write.model_fields_set and event.confidence != write.confidence
            )
            materially_changed = (
                event.deleted_at is not None
                or confidence_changed
                or any(
                    (
                        event.instrument != write.instrument,
                        not isclose(event.onset_seconds, write.onset_seconds, abs_tol=1e-9),
                        not isclose(event.duration_seconds, write.duration_seconds, abs_tol=1e-9),
                        event.velocity != write.velocity,
                        not isclose(event.beat_position, write.beat_position, abs_tol=1e-9),
                        event.measure_index != write.measure_index,
                        event.subdivision != write.subdivision,
                        not isclose(event.quantized_onset, write.quantized_onset, abs_tol=1e-9),
                    )
                )
            )
            if not materially_changed:
                continue
            burden.events_moved += int(
                not isclose(event.onset_seconds, write.onset_seconds, abs_tol=1e-9)
                or not isclose(event.quantized_onset, write.quantized_onset, abs_tol=1e-9)
                or event.measure_index != write.measure_index
                or not isclose(event.beat_position, write.beat_position, abs_tol=1e-9)
            )
            burden.instruments_reassigned += int(event.instrument != write.instrument)
            burden.velocities_changed += int(event.velocity != write.velocity)
            event.instrument = write.instrument
            event.onset_seconds = write.onset_seconds
            event.duration_seconds = write.duration_seconds
            event.velocity = write.velocity
            if "confidence" in write.model_fields_set:
                event.confidence = write.confidence
            event.source = EventSource.USER
            event.beat_position = write.beat_position
            event.measure_index = write.measure_index
            event.subdivision = write.subdivision
            event.quantized_onset = write.quantized_onset
            event.manually_edited = True
            event.deleted_at = None
        upserted.append(event)

    deleted: list[uuid.UUID] = []
    for event_id in payload.delete_ids:
        event = existing.get(event_id)
        if event is None or event.deleted_at is not None:
            raise not_found("Drum event")
        event.deleted_at = utcnow()
        event.manually_edited = True
        deleted.append(event_id)
        burden.events_deleted += 1

    if not upserted and not deleted:
        return [], [], None, burden

    transcription.version += 1
    project.edit_version = transcription.version
    await db.flush()
    snapshot = await current_snapshot(db, transcription.id)
    revision = await create_revision(
        db,
        transcription,
        kind=RevisionKind.AUTOSAVE,
        label=payload.revision_label,
        created_by_user_id=user_id,
        snapshot=snapshot,
    )
    if revision.id is None:
        raise RuntimeError("revision identifier was not generated")
    return upserted, deleted, revision.id, burden
