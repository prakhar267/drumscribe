import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditEvent, ProductEvent


def record_audit(
    db: AsyncSession,
    action: str,
    *,
    user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        action=action,
        user_id=user_id,
        project_id=project_id,
        request_id=request_id,
        metadata_json=metadata or {},
    )
    db.add(event)
    return event


def record_product_event(
    db: AsyncSession,
    name: str,
    *,
    user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    properties: dict[str, Any] | None = None,
) -> ProductEvent:
    event = ProductEvent(
        name=name,
        user_id=user_id,
        project_id=project_id,
        properties=properties or {},
    )
    db.add(event)
    return event
