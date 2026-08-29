import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Request
from sqlalchemy import select

from ...dependencies import CurrentPrincipal, DBSession, owned_project
from ...enums import AssetKind, AssetStatus
from ...errors import not_found
from ...models import AudioAsset
from ...schemas import SignedURLResponse

router = APIRouter(prefix="/projects/{project_id}/audio", tags=["private audio"])
waveform_router = APIRouter(prefix="/projects/{project_id}/waveform", tags=["waveform"])


@router.get("/{channel}/url", response_model=SignedURLResponse)
async def signed_audio_url(
    project_id: uuid.UUID,
    channel: Literal["original", "drums"],
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
) -> SignedURLResponse:
    project = await owned_project(str(project_id), db, principal)
    if channel == "original":
        if project.original_asset_id is None:
            raise not_found("Audio")
        conditions = [AudioAsset.id == project.original_asset_id]
    else:
        conditions = [
            AudioAsset.project_id == project.id,
            AudioAsset.kind == AssetKind.DRUM_STEM,
        ]
    asset = (
        (
            await db.execute(
                select(AudioAsset).where(
                    *conditions,
                    AudioAsset.status == AssetStatus.VERIFIED,
                    AudioAsset.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if asset is None:
        raise not_found("Audio")
    signed = await request.app.state.storage.presign_get(
        asset.storage_key, request.app.state.settings.signed_url_ttl_seconds
    )
    return SignedURLResponse(
        url=signed.url,
        expires_at=datetime.fromtimestamp(signed.expires_at_epoch, tz=UTC),
    )


@waveform_router.get("/url", response_model=SignedURLResponse)
async def signed_waveform_url(
    project_id: uuid.UUID,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
) -> SignedURLResponse:
    project = await owned_project(str(project_id), db, principal)
    asset = (
        (
            await db.execute(
                select(AudioAsset).where(
                    AudioAsset.project_id == project.id,
                    AudioAsset.kind == AssetKind.WAVEFORM_PEAKS,
                    AudioAsset.status == AssetStatus.VERIFIED,
                    AudioAsset.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if asset is None:
        raise not_found("Waveform")
    signed = await request.app.state.storage.presign_get(
        asset.storage_key, request.app.state.settings.signed_url_ttl_seconds
    )
    return SignedURLResponse(
        url=signed.url,
        expires_at=datetime.fromtimestamp(signed.expires_at_epoch, tz=UTC),
    )
