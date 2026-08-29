from datetime import timedelta

from sqlalchemy import exists, func, select

from ..config import Settings
from ..database import Database
from ..enums import AssetStatus, UserKind
from ..models import AudioAsset, Export, Project, Session, User
from ..security import utcnow
from .storage import PrivateStorage


class RetentionService:
    """Idempotent object cleanup driven by durable database lifecycle markers."""

    def __init__(self, settings: Settings, database: Database, storage: PrivateStorage) -> None:
        self.settings = settings
        self.database = database
        self.storage = storage

    async def run(self) -> dict[str, int]:
        now = utcnow()
        async with self.database.session_factory() as db:
            expired_exports = list(
                (
                    await db.execute(
                        select(Export).where(
                            Export.expires_at.is_not(None),
                            Export.expires_at <= now,
                            Export.storage_key.is_not(None),
                        )
                    )
                ).scalars()
            )
            expired_assets = list(
                (
                    await db.execute(
                        select(AudioAsset).where(
                            AudioAsset.status.in_(
                                {
                                    AssetStatus.DELETING,
                                    AssetStatus.PENDING_UPLOAD,
                                    AssetStatus.UPLOADED,
                                    AssetStatus.REJECTED,
                                }
                            ),
                            AudioAsset.expires_at.is_not(None),
                            AudioAsset.expires_at <= now,
                        )
                    )
                ).scalars()
            )
            anonymous_users = list(
                (
                    await db.execute(
                        select(User).where(
                            User.kind == UserKind.ANONYMOUS,
                            User.deleted_at.is_(None),
                            User.created_at
                            < now - timedelta(hours=self.settings.anonymous_retention_hours),
                            ~exists(
                                select(Session.id).where(
                                    Session.user_id == User.id,
                                    Session.revoked_at.is_(None),
                                    func.coalesce(Session.last_seen_at, Session.created_at)
                                    >= now
                                    - timedelta(hours=self.settings.anonymous_retention_hours),
                                )
                            ),
                            ~exists(
                                select(Project.id).where(
                                    Project.owner_id == User.id,
                                    Project.deleted_at.is_(None),
                                    Project.updated_at
                                    >= now
                                    - timedelta(hours=self.settings.anonymous_retention_hours),
                                )
                            ),
                        )
                    )
                ).scalars()
            )
            user_ids = [user.id for user in anonymous_users]
            projects = (
                list(
                    (
                        await db.execute(
                            select(Project).where(
                                Project.owner_id.in_(user_ids),
                                Project.deleted_at.is_(None),
                            )
                        )
                    ).scalars()
                )
                if user_ids
                else []
            )
            project_ids = [project.id for project in projects]
            assets = (
                list(
                    (
                        await db.execute(
                            select(AudioAsset).where(
                                AudioAsset.project_id.in_(project_ids),
                                AudioAsset.status != AssetStatus.DELETED,
                            )
                        )
                    ).scalars()
                )
                if project_ids
                else []
            )
            assets_to_purge = {asset.id: asset for asset in [*expired_assets, *assets]}
            keys = {export.storage_key for export in expired_exports if export.storage_key}
            keys.update(asset.storage_key for asset in assets_to_purge.values())
            await self.storage.delete_many(sorted(keys))
            for export in expired_exports:
                export.deleted_at = now
                export.storage_key = None
            for asset in assets_to_purge.values():
                asset.status = AssetStatus.DELETED
                asset.deleted_at = asset.deleted_at or now
                asset.expires_at = None
            for project in projects:
                project.deleted_at = now
            for user in anonymous_users:
                user.deleted_at = now
            if user_ids:
                sessions = list(
                    (
                        await db.execute(
                            select(Session).where(
                                Session.user_id.in_(user_ids),
                                Session.revoked_at.is_(None),
                            )
                        )
                    ).scalars()
                )
                for session in sessions:
                    session.revoked_at = now
            await db.commit()
            return {
                "expiredExports": len(expired_exports),
                "anonymousUsers": len(anonymous_users),
                "assets": len(assets_to_purge),
            }
