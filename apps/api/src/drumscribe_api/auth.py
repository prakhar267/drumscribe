from dataclasses import dataclass
from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .enums import UserKind
from .errors import APIError
from .models import MagicLink, Project, Session, User
from .security import as_utc, opaque_token, privacy_hash, token_hash, utcnow


@dataclass(frozen=True, slots=True)
class Principal:
    user: User
    session: Session


def normalize_email(email: str) -> str:
    return email.strip().casefold()


async def create_session(
    db: AsyncSession,
    user: User,
    settings: Settings,
) -> tuple[Session, str]:
    raw_token = opaque_token()
    session = Session(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        expires_at=utcnow() + timedelta(seconds=settings.session_ttl_seconds),
    )
    db.add(session)
    await db.flush()
    return session, raw_token


def set_session_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.cookie_domain,
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        domain=settings.cookie_domain,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def session_token_from_request(request: Request, settings: Settings) -> str | None:
    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.cookies.get(settings.session_cookie_name)


async def resolve_principal(
    db: AsyncSession,
    token: str | None,
) -> Principal | None:
    if not token:
        return None
    row = await db.execute(
        select(Session, User)
        .join(User, User.id == Session.user_id)
        .where(
            Session.token_hash == token_hash(token),
            Session.revoked_at.is_(None),
            Session.expires_at > utcnow(),
            User.deleted_at.is_(None),
        )
    )
    result = row.one_or_none()
    if result is None:
        return None
    session, user = result
    now = utcnow()
    if session.last_seen_at is None or as_utc(session.last_seen_at) < now - timedelta(minutes=5):
        session.last_seen_at = now
        await db.commit()
    return Principal(user=user, session=session)


async def create_anonymous_principal(db: AsyncSession, settings: Settings) -> tuple[Principal, str]:
    user = User(kind=UserKind.ANONYMOUS)
    db.add(user)
    await db.flush()
    session, raw_token = await create_session(db, user, settings)
    return Principal(user=user, session=session), raw_token


async def issue_magic_link(
    db: AsyncSession,
    email: str,
    settings: Settings,
    client_ip: str | None,
) -> str:
    normalized = normalize_email(email)
    raw_token = opaque_token(40)
    link = MagicLink(
        email=normalized,
        token_hash=token_hash(raw_token),
        expires_at=utcnow() + timedelta(seconds=settings.magic_link_ttl_seconds),
        requested_ip_hash=(
            privacy_hash(client_ip, settings.session_secret_bytes) if client_ip else None
        ),
    )
    db.add(link)
    await db.flush()
    return raw_token


async def consume_magic_link(
    db: AsyncSession,
    raw_token: str,
    settings: Settings,
    current: Principal | None,
) -> tuple[Principal, str | None]:
    claimed = (
        (
            await db.execute(
                update(MagicLink)
                .where(
                    MagicLink.token_hash == token_hash(raw_token),
                    MagicLink.consumed_at.is_(None),
                    MagicLink.expires_at > utcnow(),
                )
                .values(consumed_at=utcnow())
                .returning(MagicLink.email)
            )
        )
        .mappings()
        .one_or_none()
    )
    if claimed is None:
        raise APIError(400, "MAGIC_LINK_INVALID", "This sign-in link is invalid or expired.")
    link_email = str(claimed["email"])

    target = (
        await db.execute(
            select(User).where(
                User.email == link_email,
                User.deleted_at.is_(None),
                User.kind == UserKind.REGISTERED,
            )
        )
    ).scalar_one_or_none()

    raw_session_token: str | None = None
    if current is not None and current.user.kind == UserKind.ANONYMOUS:
        anonymous = current.user
        if target is None:
            anonymous.kind = UserKind.REGISTERED
            anonymous.email = link_email
            target = anonymous
            principal = current
        else:
            await db.execute(
                update(Project)
                .where(Project.owner_id == anonymous.id, Project.deleted_at.is_(None))
                .values(owner_id=target.id)
            )
            await db.execute(
                update(Session)
                .where(Session.user_id == anonymous.id, Session.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
            anonymous.deleted_at = utcnow()
            new_session, raw_session_token = await create_session(db, target, settings)
            principal = Principal(user=target, session=new_session)
    else:
        if target is None:
            target = User(email=link_email, kind=UserKind.REGISTERED)
            db.add(target)
            await db.flush()
        new_session, raw_session_token = await create_session(db, target, settings)
        principal = Principal(user=target, session=new_session)

    await db.flush()
    return principal, raw_session_token


async def require_registered(principal: Principal) -> None:
    if principal.user.kind != UserKind.REGISTERED:
        raise APIError(
            403,
            "ACCOUNT_REQUIRED",
            "Create an account to use this feature; your anonymous project will be preserved.",
        )
