import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Header, Request, status
from sqlalchemy import select

from ...dependencies import CurrentPrincipal, DBSession, active_transcription, owned_project
from ...enums import ExportStatus
from ...errors import APIError, not_found
from ...models import Export, Project
from ...schemas import ExportRequest, ExportResponse, SignedURLResponse
from ...security import as_utc, utcnow
from ...services.audit import record_audit, record_product_event
from ...services.exports import create_or_get_export

router = APIRouter(tags=["exports"])


def export_response(export: Export) -> ExportResponse:
    return ExportResponse(
        id=export.id,
        project_id=export.project_id,
        format=export.format,
        status=export.status,
        expires_at=export.expires_at,
        error_message=(
            "The export could not be generated. Please retry."
            if export.status == ExportStatus.FAILED
            else None
        ),
        created_at=export.created_at,
        updated_at=export.updated_at,
    )


@router.post(
    "/projects/{project_id}/exports",
    response_model=ExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_export(
    project_id: uuid.UUID,
    payload: ExportRequest,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ExportResponse:
    if not idempotency_key or len(idempotency_key.strip()) > 128:
        raise APIError(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Provide a valid Idempotency-Key header for this export.",
        )
    project = await owned_project(str(project_id), db, principal)
    transcription = await active_transcription(db, project)
    export, created = await create_or_get_export(
        db,
        project=project,
        transcription=transcription,
        export_format=payload.format,
        idempotency_key=idempotency_key.strip(),
    )
    if created:
        record_audit(
            db,
            "export.requested",
            user_id=principal.user.id,
            project_id=project.id,
            request_id=getattr(request.state, "request_id", None),
            metadata={"exportId": str(export.id), "format": export.format.value},
        )
    await db.commit()
    if created:
        await request.app.state.queue.enqueue_export(export.id)
    return export_response(export)


async def _owned_export(db: DBSession, export_id: uuid.UUID, owner_id: uuid.UUID) -> Export:
    export = (
        await db.execute(
            select(Export)
            .join(Project, Project.id == Export.project_id)
            .where(
                Export.id == export_id,
                Export.deleted_at.is_(None),
                Project.owner_id == owner_id,
                Project.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if export is None:
        raise not_found("Export")
    return export


@router.get("/exports/{export_id}", response_model=ExportResponse)
async def get_export(
    export_id: uuid.UUID,
    db: DBSession,
    principal: CurrentPrincipal,
) -> ExportResponse:
    return export_response(await _owned_export(db, export_id, principal.user.id))


@router.get("/exports/{export_id}/download", response_model=SignedURLResponse)
async def download_export(
    export_id: uuid.UUID,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
) -> SignedURLResponse:
    export = await _owned_export(db, export_id, principal.user.id)
    if export.status != ExportStatus.READY or not export.storage_key:
        raise APIError(409, "EXPORT_NOT_READY", "This export is not ready to download.")
    if export.expires_at is not None and as_utc(export.expires_at) < utcnow():
        raise APIError(410, "EXPORT_EXPIRED", "This export has expired. Generate a new one.")
    signed = await request.app.state.storage.presign_get(
        export.storage_key, request.app.state.settings.signed_url_ttl_seconds
    )
    record_product_event(
        db,
        "export_downloaded",
        user_id=principal.user.id,
        project_id=export.project_id,
        properties={"format": export.format.value},
    )
    await db.commit()
    return SignedURLResponse(
        url=signed.url,
        expires_at=datetime.fromtimestamp(signed.expires_at_epoch, tz=UTC),
    )
