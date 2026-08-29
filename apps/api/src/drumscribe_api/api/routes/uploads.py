import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from ...dependencies import AppSettings, CurrentPrincipal, DBSession, owned_project
from ...enums import AssetKind, AssetStatus, ProjectStatus
from ...errors import APIError, not_found
from ...models import AudioAsset, Project
from ...schemas import (
    AssetResponse,
    PresignedUploadResponse,
    PresignUploadRequest,
    UploadCompleteRequest,
)
from ...security import utcnow
from ...services.audio import validate_upload_contract
from ...services.audit import record_audit, record_product_event
from ...services.storage import LocalPrivateStorage, ObjectNotFoundError

router = APIRouter(tags=["uploads"])


def _safe_filename(value: str) -> str:
    filename = Path(value.replace("\\", "/")).name
    filename = "".join(character for character in filename if character.isprintable())[:255]
    return filename or "audio-upload"


@router.post(
    "/projects/{project_id}/uploads/presign",
    response_model=PresignedUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def presign_upload(
    project_id: uuid.UUID,
    payload: PresignUploadRequest,
    request: Request,
    db: DBSession,
    settings: AppSettings,
    principal: CurrentPrincipal,
) -> PresignedUploadResponse:
    project = await owned_project(str(project_id), db, principal)
    content_type = validate_upload_contract(payload.content_type, payload.size_bytes, settings)
    asset_id = uuid.uuid4()
    storage_key = (
        f"users/{principal.user.id}/projects/{project.id}/originals/{asset_id}"
    )
    asset = AudioAsset(
        id=asset_id,
        project_id=project.id,
        kind=AssetKind.ORIGINAL,
        status=AssetStatus.PENDING_UPLOAD,
        storage_key=storage_key,
        original_filename=_safe_filename(payload.filename),
        content_type=content_type,
        size_bytes=payload.size_bytes,
    )
    db.add(asset)
    project.status = ProjectStatus.UPLOADING
    record_audit(
        db,
        "upload.rights_confirmed",
        user_id=principal.user.id,
        project_id=project.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"assetId": str(asset.id), "sizeBytes": payload.size_bytes},
    )
    signed = await request.app.state.storage.presign_put(
        storage_key,
        content_type,
        payload.size_bytes,
        settings.signed_url_ttl_seconds,
    )
    asset.expires_at = datetime.fromtimestamp(signed.expires_at_epoch, tz=UTC)
    await db.commit()
    return PresignedUploadResponse(
        asset_id=asset.id,
        upload_url=signed.url,
        required_headers=signed.required_headers,
        expires_at=datetime.fromtimestamp(signed.expires_at_epoch, tz=UTC),
        max_size_bytes=settings.max_upload_bytes,
    )


@router.post("/uploads/{asset_id}/complete", response_model=AssetResponse)
async def complete_upload(
    asset_id: uuid.UUID,
    payload: UploadCompleteRequest,
    request: Request,
    db: DBSession,
    settings: AppSettings,
    principal: CurrentPrincipal,
) -> AssetResponse:
    asset = (
        await db.execute(
            select(AudioAsset)
            .join(Project, Project.id == AudioAsset.project_id)
            .where(
                AudioAsset.id == asset_id,
                Project.owner_id == principal.user.id,
                Project.deleted_at.is_(None),
                AudioAsset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise not_found("Upload")
    if asset.status in {AssetStatus.UPLOADED, AssetStatus.VERIFIED}:
        return AssetResponse.model_validate(asset)
    if asset.status != AssetStatus.PENDING_UPLOAD:
        raise APIError(409, "UPLOAD_NOT_COMPLETABLE", "This upload cannot be completed.")
    project = await db.get(Project, asset.project_id)
    assert project is not None
    try:
        metadata = await request.app.state.storage.head(asset.storage_key)
        if metadata.size_bytes != asset.size_bytes:
            raise APIError(
                422,
                "UPLOAD_SIZE_MISMATCH",
                "The uploaded object size does not match the signed upload request.",
            )
        validate_upload_contract(asset.content_type or "", metadata.size_bytes, settings)
        if metadata.content_type and (
            metadata.content_type.split(";", 1)[0].strip().lower()
            != (asset.content_type or "").split(";", 1)[0].strip().lower()
        ):
            raise APIError(
                422,
                "UPLOAD_CONTENT_TYPE_MISMATCH",
                "The stored object content type does not match the signed upload request.",
            )
    except ObjectNotFoundError as exc:
        raise APIError(409, "UPLOAD_MISSING", "The uploaded object was not found.") from exc
    except APIError:
        asset.status = AssetStatus.REJECTED
        asset.deleted_at = utcnow()
        asset.expires_at = utcnow()
        await db.commit()
        raise
    previous_assets = list(
        (
            await db.execute(
                select(AudioAsset).where(
                    AudioAsset.project_id == project.id,
                    AudioAsset.kind == AssetKind.ORIGINAL,
                    AudioAsset.id != asset.id,
                    AudioAsset.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    now = utcnow()
    for previous in previous_assets:
        previous.status = AssetStatus.DELETING
        previous.deleted_at = now
        previous.expires_at = now + timedelta(
            hours=settings.replaced_upload_retention_hours
        )

    # Every derived artifact is tied to the previous immutable original. Revoke it
    # immediately and let the retention worker perform idempotent object cleanup.
    derived_assets = list(
        (
            await db.execute(
                select(AudioAsset).where(
                    AudioAsset.project_id == project.id,
                    AudioAsset.kind != AssetKind.ORIGINAL,
                    AudioAsset.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    for derived in derived_assets:
        derived.status = AssetStatus.DELETING
        derived.deleted_at = now
        derived.expires_at = now

    asset.status = AssetStatus.UPLOADED
    asset.deleted_at = None
    asset.expires_at = now + timedelta(hours=settings.unprocessed_upload_retention_hours)
    asset.size_bytes = metadata.size_bytes
    asset.etag = payload.etag or metadata.etag
    project.original_asset_id = asset.id
    project.active_transcription_id = None
    project.edit_version = 0
    project.duration_seconds = None
    project.status = ProjectStatus.UPLOADED
    record_audit(
        db,
        "upload.completed",
        user_id=principal.user.id,
        project_id=project.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={
            "assetId": str(asset.id),
            "sizeBytes": asset.size_bytes,
            "pendingBackgroundValidation": True,
        },
    )
    record_product_event(
        db,
        "upload_completed",
        user_id=principal.user.id,
        project_id=project.id,
        properties={"sizeBytes": metadata.size_bytes, "pendingValidation": True},
    )
    await db.commit()
    return AssetResponse.model_validate(asset)


@router.put("/storage/local/{encoded_key}", include_in_schema=False)
async def local_signed_upload(
    encoded_key: str,
    request: Request,
    settings: AppSettings,
    expires: int = Query(),
    signature: str = Query(min_length=64, max_length=64),
    content_type: str = Query(alias="contentType"),
    size: int = Query(gt=0),
) -> Response:
    storage = request.app.state.storage
    if not isinstance(storage, LocalPrivateStorage):
        raise not_found("Storage route")
    try:
        key = storage.decode_key(encoded_key)
    except (ValueError, UnicodeError):
        raise APIError(403, "SIGNED_URL_INVALID", "This signed upload URL is invalid.") from None
    if not storage.verify_signature(
        method="PUT",
        key=key,
        expires=expires,
        signature=signature,
        content_type=content_type,
        size_bytes=size,
    ):
        raise APIError(403, "SIGNED_URL_EXPIRED", "This signed upload URL is invalid or expired.")
    if size > settings.max_upload_bytes:
        raise APIError(413, "AUDIO_TOO_LARGE", "The upload exceeds the configured size limit.")
    header_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if header_type != content_type:
        raise APIError(
            400, "CONTENT_TYPE_MISMATCH", "Content-Type differs from the signed request."
        )
    header_length = request.headers.get("content-length")
    try:
        length_mismatch = header_length is not None and int(header_length) != size
    except ValueError:
        length_mismatch = True
    if length_mismatch:
        raise APIError(
            400,
            "CONTENT_LENGTH_MISMATCH",
            "Content-Length differs from the signed request.",
        )
    try:
        await storage.write_stream(
            key,
            request.stream(),
            expected_size=size,
            max_size=settings.max_upload_bytes,
        )
    except ValueError as exc:
        raise APIError(413, "UPLOAD_SIZE_MISMATCH", str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/storage/local/{encoded_key}", include_in_schema=False)
async def local_signed_download(
    encoded_key: str,
    request: Request,
    expires: int = Query(),
    signature: str = Query(min_length=64, max_length=64),
) -> FileResponse:
    storage = request.app.state.storage
    if not isinstance(storage, LocalPrivateStorage):
        raise not_found("Storage route")
    try:
        key = storage.decode_key(encoded_key)
    except (ValueError, UnicodeError):
        raise APIError(403, "SIGNED_URL_INVALID", "This signed URL is invalid.") from None
    if not storage.verify_signature(
        method="GET",
        key=key,
        expires=expires,
        signature=signature,
        now_epoch=int(time.time()),
    ):
        raise APIError(403, "SIGNED_URL_EXPIRED", "This signed URL is invalid or expired.")
    path = storage.path_for(key)
    if not path.is_file():
        raise not_found("Object")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow"},
    )
