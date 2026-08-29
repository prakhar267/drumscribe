import uuid

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from ...dependencies import CurrentPrincipal, DBSession, active_transcription, owned_project
from ...enums import RevisionKind
from ...errors import not_found
from ...models import DrumEvent, TranscriptionRevision
from ...schemas import (
    BulkEventsRequest,
    BulkEventsResponse,
    EventResponse,
    EventsResponse,
    RevisionListResponse,
    RevisionResponse,
    RevisionRestoreResponse,
)
from ...services.audit import record_audit, record_product_event
from ...services.events import apply_bulk_events
from ...services.revisions import create_revision, current_snapshot, restore_snapshot

router = APIRouter(prefix="/projects/{project_id}", tags=["transcription"])


@router.get("/events", response_model=EventsResponse)
async def get_events(
    project_id: uuid.UUID,
    db: DBSession,
    principal: CurrentPrincipal,
    measure_start: int | None = Query(default=None, alias="measureStart", ge=0),
    measure_end: int | None = Query(default=None, alias="measureEnd", ge=0),
    confidence_below: float | None = Query(default=None, alias="confidenceBelow", ge=0, le=1),
) -> EventsResponse:
    project = await owned_project(str(project_id), db, principal)
    transcription = await active_transcription(db, project)
    conditions = [
        DrumEvent.transcription_id == transcription.id,
        DrumEvent.deleted_at.is_(None),
    ]
    if measure_start is not None:
        conditions.append(DrumEvent.measure_index >= measure_start)
    if measure_end is not None:
        conditions.append(DrumEvent.measure_index <= measure_end)
    if confidence_below is not None:
        conditions.append(DrumEvent.confidence < confidence_below)
    events = list(
        (
            await db.execute(
                select(DrumEvent)
                .where(*conditions)
                .order_by(DrumEvent.quantized_onset, DrumEvent.instrument, DrumEvent.id)
            )
        ).scalars()
    )
    return EventsResponse(
        transcription_id=transcription.id,
        version=transcription.version,
        tempo_bpm=transcription.tempo_bpm,
        time_signature_numerator=transcription.time_signature_numerator,
        time_signature_denominator=transcription.time_signature_denominator,
        items=[EventResponse.model_validate(event) for event in events],
    )


@router.patch("/events/bulk", response_model=BulkEventsResponse)
@router.post("/events/bulk", response_model=BulkEventsResponse, include_in_schema=False)
async def bulk_edit_events(
    project_id: uuid.UUID,
    payload: BulkEventsRequest,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
) -> BulkEventsResponse:
    project = await owned_project(str(project_id), db, principal)
    transcription = await active_transcription(db, project)
    upserted, deleted_ids, revision_id = await apply_bulk_events(
        db,
        project=project,
        transcription=transcription,
        payload=payload,
        user_id=principal.user.id,
        max_events=request.app.state.settings.max_bulk_events,
    )
    if revision_id is not None:
        record_audit(
            db,
            "transcription.events_bulk_edited",
            user_id=principal.user.id,
            project_id=project.id,
            request_id=getattr(request.state, "request_id", None),
            metadata={
                "upsertCount": len(upserted),
                "deleteCount": len(deleted_ids),
                "revisionId": str(revision_id),
            },
        )
        record_product_event(
            db,
            "transcription_corrected",
            user_id=principal.user.id,
            project_id=project.id,
            properties={"upserts": len(upserted), "deletions": len(deleted_ids)},
        )
    await db.commit()
    return BulkEventsResponse(
        version=transcription.version,
        upserted=[EventResponse.model_validate(event) for event in upserted],
        deleted_ids=deleted_ids,
        revision_id=revision_id,
    )


@router.get("/revisions", response_model=RevisionListResponse)
async def list_revisions(
    project_id: uuid.UUID,
    db: DBSession,
    principal: CurrentPrincipal,
) -> RevisionListResponse:
    project = await owned_project(str(project_id), db, principal)
    transcription = await active_transcription(db, project)
    revisions = list(
        (
            await db.execute(
                select(TranscriptionRevision)
                .where(TranscriptionRevision.transcription_id == transcription.id)
                .order_by(TranscriptionRevision.sequence.desc())
            )
        ).scalars()
    )
    return RevisionListResponse(
        items=[
            RevisionResponse(
                id=revision.id,
                sequence=revision.sequence,
                kind=revision.kind,
                label=revision.label,
                event_count=len(revision.snapshot),
                created_at=revision.created_at,
            )
            for revision in revisions
        ]
    )


@router.post("/revisions/{revision_id}/restore", response_model=RevisionRestoreResponse)
async def restore_revision(
    project_id: uuid.UUID,
    revision_id: uuid.UUID,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
) -> RevisionRestoreResponse:
    project = await owned_project(str(project_id), db, principal)
    transcription = await active_transcription(db, project)
    revision = (
        await db.execute(
            select(TranscriptionRevision).where(
                TranscriptionRevision.id == revision_id,
                TranscriptionRevision.project_id == project.id,
                TranscriptionRevision.transcription_id == transcription.id,
            )
        )
    ).scalar_one_or_none()
    if revision is None:
        raise not_found("Revision")
    event_count = await restore_snapshot(db, transcription, revision)
    project.edit_version = transcription.version
    await db.flush()
    new_revision = await create_revision(
        db,
        transcription,
        kind=RevisionKind.RESTORE,
        label=f"Restored: {revision.label}",
        created_by_user_id=principal.user.id,
        snapshot=await current_snapshot(db, transcription.id),
    )
    record_audit(
        db,
        "transcription.revision_restored",
        user_id=principal.user.id,
        project_id=project.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={
            "sourceRevisionId": str(revision.id),
            "newRevisionId": str(new_revision.id),
        },
    )
    await db.commit()
    return RevisionRestoreResponse(
        restored_revision_id=revision.id,
        new_revision_id=new_revision.id,
        version=transcription.version,
        event_count=event_count,
    )
