import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .enums import (
    AssetKind,
    AssetStatus,
    Entitlement,
    EventSource,
    ExportFormat,
    ExportStatus,
    Instrument,
    JobErrorCode,
    JobStage,
    ProjectStatus,
    RevisionKind,
    UserKind,
    UserRole,
)
from .security import utcnow


def enum_column(enum_type: type[Any]) -> Enum:
    return Enum(enum_type, native_enum=False, validate_strings=True, length=64)


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    kind: Mapped[UserKind] = mapped_column(enum_column(UserKind), default=UserKind.ANONYMOUS)
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole), default=UserRole.USER)
    entitlement: Mapped[Entitlement] = mapped_column(
        enum_column(Entitlement), default=Entitlement.FREE_BETA
    )
    allow_model_improvement: Mapped[bool] = mapped_column(Boolean, default=False)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")
    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class Session(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class MagicLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "magic_links"

    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip_hash: Mapped[str | None] = mapped_column(String(64))


class Project(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_owner_updated", "owner_id", "updated_at"),
        Index("ix_projects_owner_title", "owner_id", "title"),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0", name="project_duration"
        ),
        CheckConstraint("edit_version >= 0", name="project_edit_version"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    artist: Mapped[str | None] = mapped_column(String(200))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus), default=ProjectStatus.DRAFT, index=True
    )
    original_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    active_transcription_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    edit_version: Mapped[int] = mapped_column(Integer, default=0)

    owner: Mapped[User] = relationship(back_populates="projects")
    assets: Mapped[list["AudioAsset"]] = relationship(back_populates="project")
    jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="project")
    transcriptions: Mapped[list["Transcription"]] = relationship(back_populates="project")


class AudioAsset(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "audio_assets"
    __table_args__ = (
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="asset_size"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="asset_duration"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[AssetKind] = mapped_column(enum_column(AssetKind), index=True)
    status: Mapped[AssetStatus] = mapped_column(
        enum_column(AssetStatus), default=AssetStatus.PENDING_UPLOAD
    )
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    codec: Mapped[str | None] = mapped_column(String(64))
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="assets")


class ProcessingJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_job_project_idempotency"),
        Index("ix_jobs_project_created", "project_id", "created_at"),
        CheckConstraint(
            "approximate_progress >= 0 AND approximate_progress <= 100",
            name="job_progress",
        ),
        CheckConstraint("retry_count >= 0", name="job_retry_count"),
        CheckConstraint(
            "total_provider_cost IS NULL OR total_provider_cost >= 0",
            name="job_provider_cost",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[JobStage] = mapped_column(enum_column(JobStage), default=JobStage.RECEIVED)
    last_completed_stage: Mapped[JobStage | None] = mapped_column(enum_column(JobStage))
    approximate_progress: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker: Mapped[str | None] = mapped_column(String(255))
    provider_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    total_provider_cost: Mapped[float | None] = mapped_column(Float)
    provider_cost_currency: Mapped[str | None] = mapped_column(String(32))
    stage_timings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[JobErrorCode | None] = mapped_column(enum_column(JobErrorCode))
    error_detail: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="jobs")
    model_runs: Mapped[list["ModelRun"]] = relationship(back_populates="job")


class ModelRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_runs"
    __table_args__ = (
        CheckConstraint("cost_amount IS NULL OR cost_amount >= 0", name="model_run_cost"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(128))
    provider_category: Mapped[str] = mapped_column(String(64), default="TEST_FIXTURE")
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    model_name: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(128))
    model_hash: Mapped[str | None] = mapped_column(String(128))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    hardware_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw_provider_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_category: Mapped[str | None] = mapped_column(String(64))
    cost_amount: Mapped[float | None] = mapped_column(Float)
    cost_currency: Mapped[str | None] = mapped_column(String(32))
    retention_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contract_reference: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    job: Mapped[ProcessingJob] = relationship(back_populates="model_runs")


class Transcription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transcriptions"
    __table_args__ = (
        CheckConstraint("tempo_bpm >= 20 AND tempo_bpm <= 400", name="transcription_tempo"),
        CheckConstraint("time_signature_numerator >= 1", name="time_signature_numerator"),
        CheckConstraint(
            "time_signature_denominator IN (1, 2, 4, 8, 16, 32)",
            name="time_signature_denominator",
        ),
        CheckConstraint("version >= 1", name="transcription_version"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="SET NULL")
    )
    tempo_bpm: Mapped[float] = mapped_column(Float, default=120.0)
    time_signature_numerator: Mapped[int] = mapped_column(Integer, default=4)
    time_signature_denominator: Mapped[int] = mapped_column(Integer, default=4)
    tempo_map: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    quality_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)

    project: Mapped[Project] = relationship(back_populates="transcriptions")
    events: Mapped[list["DrumEvent"]] = relationship(back_populates="transcription")
    revisions: Mapped[list["TranscriptionRevision"]] = relationship(back_populates="transcription")


class DrumEvent(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "drum_events"
    __table_args__ = (
        Index("ix_events_transcription_onset", "transcription_id", "quantized_onset"),
        Index("ix_events_project_measure", "project_id", "measure_index"),
        CheckConstraint("onset_seconds >= 0", name="event_onset"),
        CheckConstraint("duration_seconds > 0", name="event_duration"),
        CheckConstraint("velocity >= 1 AND velocity <= 127", name="event_velocity"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="event_confidence",
        ),
        CheckConstraint("measure_index >= 0", name="event_measure"),
        CheckConstraint("quantized_onset >= 0", name="event_quantized_onset"),
    )

    transcription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcriptions.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    instrument: Mapped[Instrument] = mapped_column(enum_column(Instrument))
    onset_seconds: Mapped[float] = mapped_column(Float)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.08)
    velocity: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[EventSource] = mapped_column(enum_column(EventSource))
    beat_position: Mapped[float] = mapped_column(Float)
    measure_index: Mapped[int] = mapped_column(Integer)
    subdivision: Mapped[str] = mapped_column(String(32), default="1/16")
    quantized_onset: Mapped[float] = mapped_column(Float)
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False)

    transcription: Mapped[Transcription] = relationship(back_populates="events")


class TranscriptionRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transcription_revisions"
    __table_args__ = (
        UniqueConstraint("transcription_id", "sequence", name="uq_revision_sequence"),
    )

    transcription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcriptions.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[RevisionKind] = mapped_column(enum_column(RevisionKind))
    label: Mapped[str] = mapped_column(String(200))
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    transcription: Mapped[Transcription] = relationship(back_populates="revisions")


class Export(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "exports"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_export_idempotency"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    transcription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcriptions.id", ondelete="CASCADE")
    )
    format: Mapped[ExportFormat] = mapped_column(enum_column(ExportFormat))
    status: Mapped[ExportStatus] = mapped_column(
        enum_column(ExportStatus), default=ExportStatus.QUEUED
    )
    storage_key: Mapped[str | None] = mapped_column(String(1024), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    error_detail: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ProductEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "product_events"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class UserFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_feedback"
    __table_args__ = (
        CheckConstraint("rating IS NULL OR (rating >= 1 AND rating <= 5)", name="feedback_rating"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer)
