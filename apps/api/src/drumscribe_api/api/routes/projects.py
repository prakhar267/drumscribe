import uuid
from datetime import timedelta
from typing import Literal

import structlog
from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, select

from ...dependencies import (
    AppSettings,
    CurrentPrincipal,
    DBSession,
    active_transcription,
    owned_project,
)
from ...enums import AssetStatus, EventSource, ProjectStatus, RevisionKind
from ...errors import APIError
from ...models import AudioAsset, DrumEvent, Project, Transcription
from ...schemas import (
    DeleteResponse,
    DuplicateProjectRequest,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from ...security import as_utc, utcnow
from ...services.audit import record_audit
from ...services.revisions import create_revision
from ...services.storage import ObjectNotFoundError, PrivateStorage

router = APIRouter(prefix="/projects", tags=["projects"])
logger = structlog.get_logger(__name__)

StorageMove = tuple[str, str, str]


async def _revert_storage_moves(
    storage: PrivateStorage, moves: list[StorageMove]
) -> None:
    for old_key, quarantine_key, content_type in reversed(moves):
        try:
            await storage.copy(quarantine_key, old_key, content_type)
            await storage.delete_many([quarantine_key])
        except Exception:
            logger.exception(
                "asset_quarantine_revert_failed",
                old_key=old_key,
                quarantine_key=quarantine_key,
            )


async def _quarantine_assets(
    storage: PrivateStorage,
    project: Project,
    assets: list[AudioAsset],
) -> list[StorageMove]:
    moves: list[StorageMove] = []
    try:
        for asset in assets:
            old_key = asset.storage_key
            quarantine_key = (
                f"quarantine/users/{project.owner_id}/projects/{project.id}/"
                f"assets/{asset.id}/{uuid.uuid4()}"
            )
            content_type = asset.content_type or "application/octet-stream"
            try:
                await storage.copy(old_key, quarantine_key, content_type)
            except ObjectNotFoundError:
                continue
            moves.append((old_key, quarantine_key, content_type))
            await storage.delete_many([old_key])
    except Exception:
        await _revert_storage_moves(storage, moves)
        raise
    return moves


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
) -> ProjectResponse:
    project = Project(
        owner_id=principal.user.id,
        title=payload.title,
        artist=payload.artist,
        status=ProjectStatus.DRAFT,
    )
    db.add(project)
    await db.flush()
    record_audit(
        db,
        "project.created",
        user_id=principal.user.id,
        project_id=project.id,
        request_id=getattr(request.state, "request_id", None),
    )
    await db.commit()
    return ProjectResponse.model_validate(project)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    db: DBSession,
    principal: CurrentPrincipal,
    q: str | None = Query(default=None, max_length=200),
    sort: Literal["recent", "oldest", "name"] = "recent",
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ProjectListResponse:
    conditions = [
        Project.owner_id == principal.user.id,
        Project.deleted_at.is_(None),
    ]
    if q and q.strip():
        conditions.append(Project.title.icontains(q.strip(), autoescape=True))
    order = {
        "recent": (Project.updated_at.desc(), Project.id.desc()),
        "oldest": (Project.created_at.asc(), Project.id.asc()),
        "name": (func.lower(Project.title).asc(), Project.id.asc()),
    }[sort]
    projects = list(
        (
            await db.execute(
                select(Project).where(*conditions).order_by(*order).limit(limit).offset(offset)
            )
        ).scalars()
    )
    total = int(await db.scalar(select(func.count(Project.id)).where(*conditions)) or 0)
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(project) for project in projects],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: DBSession,
    principal: CurrentPrincipal,
) -> ProjectResponse:
    project = await owned_project(str(project_id), db, principal)
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
) -> ProjectResponse:
    project = await owned_project(str(project_id), db, principal)
    if payload.title is not None:
        project.title = payload.title
    if "artist" in payload.model_fields_set:
        project.artist = payload.artist
    record_audit(
        db,
        "project.updated",
        user_id=principal.user.id,
        project_id=project.id,
        request_id=getattr(request.state, "request_id", None),
    )
    await db.commit()
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", response_model=DeleteResponse)
async def delete_project(
    project_id: uuid.UUID,
    request: Request,
    db: DBSession,
    settings: AppSettings,
    principal: CurrentPrincipal,
) -> DeleteResponse:
    project = await owned_project(str(project_id), db, principal)
    now = utcnow()
    project.deleted_at = now
    assets = list(
        (
            await db.execute(
                select(AudioAsset).where(
                    AudioAsset.project_id == project.id,
                    AudioAsset.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    storage = request.app.state.storage
    moves = await _quarantine_assets(storage, project, assets)
    quarantine_keys = {old_key: new_key for old_key, new_key, _ in moves}
    purge_at = now + timedelta(hours=settings.project_delete_grace_hours)
    for asset in assets:
        recoverable = asset.status == AssetStatus.VERIFIED
        asset.storage_key = quarantine_keys.get(asset.storage_key, asset.storage_key)
        asset.deleted_at = now
        asset.status = AssetStatus.DELETING
        asset.expires_at = purge_at if recoverable else now
    record_audit(
        db,
        "project.deleted",
        user_id=principal.user.id,
        project_id=project.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"recoverableForHours": settings.project_delete_grace_hours},
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await _revert_storage_moves(storage, moves)
        raise
    return DeleteResponse()


@router.post("/{project_id}/restore", response_model=ProjectResponse)
async def restore_project(
    project_id: uuid.UUID,
    request: Request,
    db: DBSession,
    settings: AppSettings,
    principal: CurrentPrincipal,
) -> ProjectResponse:
    project = await owned_project(str(project_id), db, principal, include_deleted=True)
    if project.deleted_at is None:
        return ProjectResponse.model_validate(project)
    now = utcnow()
    deleted_at = as_utc(project.deleted_at)
    if deleted_at < now - timedelta(hours=settings.project_delete_grace_hours):
        raise APIError(410, "RESTORE_WINDOW_EXPIRED", "This project's restore window has expired.")
    assets = list(
        (
            await db.execute(
                select(AudioAsset).where(
                    AudioAsset.project_id == project.id,
                    AudioAsset.status == AssetStatus.DELETING,
                    AudioAsset.deleted_at == project.deleted_at,
                    AudioAsset.expires_at.is_not(None),
                    AudioAsset.expires_at > now,
                )
            )
        ).scalars()
    )
    for asset in assets:
        asset.deleted_at = None
        asset.status = AssetStatus.VERIFIED
        asset.expires_at = None
    if project.original_asset_id is not None and not any(
        asset.id == project.original_asset_id for asset in assets
    ):
        raise APIError(
            410,
            "RESTORE_MEDIA_UNAVAILABLE",
            "This project's private audio has already been permanently deleted.",
        )
    project.deleted_at = None
    record_audit(
        db,
        "project.restored",
        user_id=principal.user.id,
        project_id=project.id,
        request_id=getattr(request.state, "request_id", None),
    )
    await db.commit()
    return ProjectResponse.model_validate(project)


@router.post(
    "/{project_id}/duplicate",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_project(
    project_id: uuid.UUID,
    payload: DuplicateProjectRequest,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
) -> ProjectResponse:
    source = await owned_project(str(project_id), db, principal)
    duplicate = Project(
        owner_id=principal.user.id,
        title=payload.title or f"{source.title} copy",
        artist=source.artist,
        duration_seconds=source.duration_seconds,
        status=(
            source.status
            if source.status not in {ProjectStatus.PROCESSING, ProjectStatus.FAILED}
            else ProjectStatus.UPLOADED
        ),
        edit_version=source.edit_version,
    )
    db.add(duplicate)
    await db.flush()

    asset_map: dict[uuid.UUID, uuid.UUID] = {}
    assets = list(
        (
            await db.execute(
                select(AudioAsset).where(
                    AudioAsset.project_id == source.id,
                    AudioAsset.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    for source_asset in assets:
        asset_id = uuid.uuid4()
        destination_key = (
            f"users/{principal.user.id}/projects/{duplicate.id}/copies/{asset_id}"
        )
        await request.app.state.storage.copy(
            source_asset.storage_key,
            destination_key,
            source_asset.content_type or "application/octet-stream",
        )
        cloned_asset = AudioAsset(
            id=asset_id,
            project_id=duplicate.id,
            kind=source_asset.kind,
            status=source_asset.status,
            storage_key=destination_key,
            original_filename=source_asset.original_filename,
            content_type=source_asset.content_type,
            size_bytes=source_asset.size_bytes,
            duration_seconds=source_asset.duration_seconds,
            codec=source_asset.codec,
            sample_rate=source_asset.sample_rate,
            channels=source_asset.channels,
        )
        db.add(cloned_asset)
        asset_map[source_asset.id] = cloned_asset.id
    if source.original_asset_id:
        duplicate.original_asset_id = asset_map.get(source.original_asset_id)

    if source.active_transcription_id:
        source_transcription = await active_transcription(db, source)
        cloned_transcription = Transcription(
            project_id=duplicate.id,
            tempo_bpm=source_transcription.tempo_bpm,
            time_signature_numerator=source_transcription.time_signature_numerator,
            time_signature_denominator=source_transcription.time_signature_denominator,
            tempo_map=source_transcription.tempo_map,
            quality_summary=source_transcription.quality_summary,
            version=source_transcription.version,
        )
        db.add(cloned_transcription)
        await db.flush()
        source_events = list(
            (
                await db.execute(
                    select(DrumEvent).where(
                        DrumEvent.transcription_id == source_transcription.id,
                        DrumEvent.deleted_at.is_(None),
                    )
                )
            ).scalars()
        )
        for event in source_events:
            db.add(
                DrumEvent(
                    transcription_id=cloned_transcription.id,
                    project_id=duplicate.id,
                    instrument=event.instrument,
                    onset_seconds=event.onset_seconds,
                    duration_seconds=event.duration_seconds,
                    velocity=event.velocity,
                    confidence=event.confidence,
                    source=(EventSource.USER if event.manually_edited else event.source),
                    beat_position=event.beat_position,
                    measure_index=event.measure_index,
                    subdivision=event.subdivision,
                    quantized_onset=event.quantized_onset,
                    manually_edited=event.manually_edited,
                )
            )
        duplicate.active_transcription_id = cloned_transcription.id
        await db.flush()
        await create_revision(
            db,
            cloned_transcription,
            kind=RevisionKind.MANUAL,
            label="Duplicated project",
            created_by_user_id=principal.user.id,
        )

    record_audit(
        db,
        "project.duplicated",
        user_id=principal.user.id,
        project_id=duplicate.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"sourceProjectId": str(source.id)},
    )
    await db.commit()
    return ProjectResponse.model_validate(duplicate)
