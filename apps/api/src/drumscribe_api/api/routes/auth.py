import structlog
from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from ...auth import (
    clear_session_cookie,
    consume_magic_link,
    create_anonymous_principal,
    issue_magic_link,
    set_session_cookie,
)
from ...dependencies import (
    AppSettings,
    CurrentPrincipal,
    DBSession,
    OptionalPrincipal,
)
from ...enums import AssetStatus
from ...models import AudioAsset, Export, Project, Session
from ...schemas import (
    AccountDeleteRequest,
    AccountUpdate,
    DeleteResponse,
    MagicLinkConsume,
    MagicLinkRequest,
    MagicLinkRequested,
    SessionResponse,
    UserResponse,
)
from ...security import utcnow
from ...services.audit import record_audit
from ...services.magic_links import MagicLinkDelivery

router = APIRouter(prefix="/auth", tags=["authentication"])
account_router = APIRouter(prefix="/account", tags=["account"])
logger = structlog.get_logger(__name__)


def _session_response(principal: CurrentPrincipal, settings: AppSettings) -> SessionResponse:
    return SessionResponse(
        user=UserResponse.model_validate(principal.user),
        expires_at=principal.session.expires_at,
        feature_flags=settings.feature_flags,
    )


@router.post(
    "/anonymous-session",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def anonymous_session(
    response: Response,
    request: Request,
    db: DBSession,
    settings: AppSettings,
    current: OptionalPrincipal,
) -> SessionResponse:
    if current is not None:
        response.status_code = status.HTTP_200_OK
        return _session_response(current, settings)
    principal, raw_token = await create_anonymous_principal(db, settings)
    record_audit(
        db,
        "session.anonymous_created",
        user_id=principal.user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    await db.commit()
    set_session_cookie(response, raw_token, settings)
    return _session_response(principal, settings)


@router.post(
    "/magic-link/request",
    response_model=MagicLinkRequested,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_magic_link(
    payload: MagicLinkRequest,
    request: Request,
    db: DBSession,
    settings: AppSettings,
) -> MagicLinkRequested:
    token = await issue_magic_link(
        db,
        str(payload.email),
        settings,
        request.client.host if request.client else None,
    )
    await db.commit()
    await MagicLinkDelivery(settings).deliver(str(payload.email).casefold(), token)
    return MagicLinkRequested(dev_token=token if settings.dev_expose_magic_link else None)


@router.post("/magic-link/consume", response_model=SessionResponse)
async def consume_link(
    payload: MagicLinkConsume,
    response: Response,
    request: Request,
    db: DBSession,
    settings: AppSettings,
    current: OptionalPrincipal,
) -> SessionResponse:
    principal, raw_session_token = await consume_magic_link(
        db, payload.token, settings, current
    )
    record_audit(
        db,
        "account.magic_link_consumed",
        user_id=principal.user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    await db.commit()
    if raw_session_token is not None:
        set_session_cookie(response, raw_session_token, settings)
    return _session_response(principal, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: DBSession,
    settings: AppSettings,
    principal: CurrentPrincipal,
) -> None:
    principal.session.revoked_at = utcnow()
    await db.commit()
    clear_session_cookie(response, settings)


@account_router.get("/me", response_model=UserResponse)
async def account_me(principal: CurrentPrincipal) -> UserResponse:
    return UserResponse.model_validate(principal.user)


@account_router.patch("/me", response_model=UserResponse)
async def update_account(
    payload: AccountUpdate,
    db: DBSession,
    principal: CurrentPrincipal,
) -> UserResponse:
    principal.user.allow_model_improvement = payload.allow_model_improvement
    record_audit(
        db,
        "account.model_improvement_consent_updated",
        user_id=principal.user.id,
        metadata={"enabled": payload.allow_model_improvement},
    )
    await db.commit()
    return UserResponse.model_validate(principal.user)


@account_router.delete("", response_model=DeleteResponse)
async def delete_account(
    payload: AccountDeleteRequest,
    response: Response,
    request: Request,
    db: DBSession,
    settings: AppSettings,
    principal: CurrentPrincipal,
) -> DeleteResponse:
    del payload
    projects = list(
        (
            await db.execute(
                select(Project).where(
                    Project.owner_id == principal.user.id,
                    Project.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    project_ids = [project.id for project in projects]
    assets = (
        list(
            (
                await db.execute(
                    select(AudioAsset).where(AudioAsset.project_id.in_(project_ids))
                )
            ).scalars()
        )
        if project_ids
        else []
    )
    exports = (
        list(
            (
                await db.execute(
                    select(Export).where(
                        Export.project_id.in_(project_ids),
                        Export.deleted_at.is_(None),
                    )
                )
            ).scalars()
        )
        if project_ids
        else []
    )
    now = utcnow()
    for project in projects:
        project.deleted_at = now
    for asset in assets:
        asset.deleted_at = now
        asset.status = AssetStatus.DELETING
        asset.expires_at = now
    for export in exports:
        export.deleted_at = now
        export.expires_at = now
    principal.user.deleted_at = now
    # Release the unique identity key while retaining the opaque tombstone row.
    principal.user.email = None
    sessions = list(
        (
            await db.execute(
                select(Session).where(
                    Session.user_id == principal.user.id,
                    Session.revoked_at.is_(None),
                )
            )
        ).scalars()
    )
    for session in sessions:
        session.revoked_at = now
    record_audit(
        db,
        "account.deleted",
        user_id=principal.user.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={
            "projectCount": len(projects),
            "assetCount": len(assets),
            "exportCount": len(exports),
        },
    )
    await db.commit()
    storage_keys = [asset.storage_key for asset in assets]
    storage_keys.extend(export.storage_key for export in exports if export.storage_key)
    try:
        await request.app.state.storage.delete_many(storage_keys)
    except Exception as exc:
        # The committed DELETING/expiry markers make this retryable by retention;
        # account access is already revoked regardless of object-store availability.
        logger.warning(
            "account_storage_cleanup_deferred",
            user_id=str(principal.user.id),
            object_count=len(storage_keys),
            error_type=type(exc).__name__,
        )
    else:
        for asset in assets:
            asset.status = AssetStatus.DELETED
            asset.expires_at = None
        for export in exports:
            export.storage_key = None
        await db.commit()
    clear_session_cookie(response, settings)
    return DeleteResponse()
