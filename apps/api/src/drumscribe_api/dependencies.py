from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal, resolve_principal, session_token_from_request
from .config import Settings
from .database import Database
from .enums import UserRole
from .errors import APIError, not_found
from .models import Project, Transcription


def get_settings_from_request(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


async def get_db(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async with database.session_factory() as session:
        yield session


async def optional_principal(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_from_request)],
) -> Principal | None:
    token = session_token_from_request(request, settings)
    return await resolve_principal(db, token)


async def current_principal(
    principal: Annotated[Principal | None, Depends(optional_principal)],
) -> Principal:
    if principal is None:
        raise APIError(
            401,
            "AUTHENTICATION_REQUIRED",
            "A valid DrumScribe session is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


async def admin_principal(
    principal: Annotated[Principal, Depends(current_principal)],
) -> Principal:
    if principal.user.role != UserRole.ADMIN:
        raise APIError(403, "ADMIN_REQUIRED", "Administrator access is required.")
    return principal


async def owned_project(
    project_id: str,
    db: AsyncSession,
    principal: Principal,
    *,
    include_deleted: bool = False,
) -> Project:
    try:
        import uuid

        project_uuid = uuid.UUID(project_id)
    except (ValueError, AttributeError):
        raise not_found("Project") from None
    conditions = [Project.id == project_uuid, Project.owner_id == principal.user.id]
    if not include_deleted:
        conditions.append(Project.deleted_at.is_(None))
    project = (await db.execute(select(Project).where(*conditions))).scalar_one_or_none()
    if project is None:
        raise not_found("Project")
    return project


async def active_transcription(db: AsyncSession, project: Project) -> Transcription:
    if project.active_transcription_id is None:
        raise APIError(409, "TRANSCRIPTION_NOT_READY", "This project's chart is not ready yet.")
    transcription = (
        await db.execute(
            select(Transcription).where(
                Transcription.id == project.active_transcription_id,
                Transcription.project_id == project.id,
            )
        )
    ).scalar_one_or_none()
    if transcription is None:
        raise APIError(409, "TRANSCRIPTION_NOT_READY", "This project's chart is not ready yet.")
    return transcription


DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
OptionalPrincipal = Annotated[Principal | None, Depends(optional_principal)]
AdminPrincipal = Annotated[Principal, Depends(admin_principal)]
AppSettings = Annotated[Settings, Depends(get_settings_from_request)]
