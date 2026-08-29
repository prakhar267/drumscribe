import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

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


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class HealthResponse(APIModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


class LivenessResponse(APIModel):
    status: Literal["ok"] = "ok"
    version: str


class DependencyHealthResponse(APIModel):
    status: Literal["ok", "unavailable"]
    latency_ms: float = Field(ge=0)


class ReadinessResponse(APIModel):
    status: Literal["ready", "unready"]
    checks: dict[str, DependencyHealthResponse]
    version: str


class UserResponse(APIModel):
    id: uuid.UUID
    email: str | None
    kind: UserKind
    role: UserRole
    entitlement: Entitlement
    allow_model_improvement: bool
    created_at: datetime


class SessionResponse(APIModel):
    user: UserResponse
    expires_at: datetime
    feature_flags: dict[str, bool]


class MagicLinkRequest(APIModel):
    email: EmailStr


class MagicLinkRequested(APIModel):
    accepted: Literal[True] = True
    dev_token: str | None = None


class MagicLinkConsume(APIModel):
    token: str = Field(min_length=32, max_length=256)


class AccountUpdate(APIModel):
    allow_model_improvement: bool


class AccountDeleteRequest(APIModel):
    confirmation: Literal["DELETE MY ACCOUNT"]


class ProjectCreate(APIModel):
    title: str = Field(default="Untitled transcription", min_length=1, max_length=200)
    artist: str | None = Field(default=None, max_length=200)

    @field_validator("title", "artist")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = " ".join(value.split())
        if not clean:
            raise ValueError("must not be blank")
        return clean


class ProjectUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    artist: str | None = Field(default=None, max_length=200)

    @field_validator("title", "artist")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = " ".join(value.split())
        if not clean:
            raise ValueError("must not be blank")
        return clean


class ProjectResponse(APIModel):
    id: uuid.UUID
    title: str
    artist: str | None
    duration_seconds: float | None
    status: ProjectStatus
    original_asset_id: uuid.UUID | None
    active_transcription_id: uuid.UUID | None
    edit_version: int
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(APIModel):
    items: list[ProjectResponse]
    total: int
    limit: int
    offset: int


class DuplicateProjectRequest(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


class PresignUploadRequest(APIModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(gt=0)
    right_to_upload_confirmed: Literal[True]


class PresignedUploadResponse(APIModel):
    asset_id: uuid.UUID
    upload_url: str
    method: Literal["PUT"] = "PUT"
    required_headers: dict[str, str]
    expires_at: datetime
    max_size_bytes: int


class UploadCompleteRequest(APIModel):
    etag: str | None = Field(default=None, max_length=255)


class AssetResponse(APIModel):
    id: uuid.UUID
    kind: AssetKind
    status: AssetStatus
    content_type: str | None
    size_bytes: int | None
    duration_seconds: float | None
    codec: str | None
    sample_rate: int | None
    channels: int | None


class ProcessingStartRequest(APIModel):
    provider: str | None = Field(default=None, max_length=128)


class JobResponse(APIModel):
    id: uuid.UUID
    project_id: uuid.UUID
    stage: JobStage
    friendly_stage: str
    approximate_progress: int
    progress_is_approximate: Literal[True] = True
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None
    error_code: JobErrorCode | None
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime


class EventWrite(APIModel):
    id: uuid.UUID | None = None
    instrument: Instrument
    onset_seconds: float = Field(ge=0)
    duration_seconds: float = Field(default=0.08, gt=0, le=10)
    velocity: int = Field(default=100, ge=1, le=127)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: EventSource = EventSource.USER
    beat_position: float = Field(ge=0)
    measure_index: int = Field(ge=0)
    subdivision: Literal["1/4", "1/8", "1/16", "1/32", "1/8T", "1/16T"] = "1/16"
    quantized_onset: float = Field(ge=0)


class EventResponse(EventWrite):
    id: uuid.UUID
    manually_edited: bool
    created_at: datetime
    updated_at: datetime


class EventsResponse(APIModel):
    transcription_id: uuid.UUID
    version: int
    tempo_bpm: float
    time_signature_numerator: int
    time_signature_denominator: int
    items: list[EventResponse]


class BulkEventsRequest(APIModel):
    upserts: list[EventWrite] = Field(default_factory=list)
    delete_ids: list[uuid.UUID] = Field(default_factory=list)
    expected_version: int = Field(ge=1)
    revision_label: str = Field(default="Autosave", min_length=1, max_length=200)

    @field_validator("delete_ids")
    @classmethod
    def unique_deletions(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("deleteIds must not contain duplicates")
        return value

    @field_validator("upserts")
    @classmethod
    def unique_upserts(cls, value: list[EventWrite]) -> list[EventWrite]:
        ids = [item.id for item in value if item.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("upserts must not contain duplicate ids")
        return value

    @model_validator(mode="after")
    def disjoint_operations(self) -> "BulkEventsRequest":
        upsert_ids = {item.id for item in self.upserts if item.id is not None}
        if upsert_ids & set(self.delete_ids):
            raise ValueError("an event cannot be upserted and deleted in the same batch")
        return self


class BulkEventsResponse(APIModel):
    version: int
    upserted: list[EventResponse]
    deleted_ids: list[uuid.UUID]
    revision_id: uuid.UUID | None


class RevisionResponse(APIModel):
    id: uuid.UUID
    sequence: int
    kind: RevisionKind
    label: str
    event_count: int
    created_at: datetime


class RevisionListResponse(APIModel):
    items: list[RevisionResponse]


class RevisionRestoreResponse(APIModel):
    restored_revision_id: uuid.UUID
    new_revision_id: uuid.UUID
    version: int
    event_count: int


class ExportRequest(APIModel):
    format: ExportFormat


class ExportResponse(APIModel):
    id: uuid.UUID
    project_id: uuid.UUID
    format: ExportFormat
    status: ExportStatus
    expires_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class SignedURLResponse(APIModel):
    url: str
    expires_at: datetime


class DeleteResponse(APIModel):
    deleted: Literal[True] = True


class AdminModelRun(APIModel):
    provider: str
    provider_category: str
    provider_request_id: str | None
    model_name: str
    model_version: str
    model_hash: str | None
    duration_seconds: float | None
    parameters: dict[str, Any]
    hardware_metadata: dict[str, Any]
    raw_provider_metadata: dict[str, Any]
    error_category: str | None
    cost_amount: float | None
    cost_currency: str | None
    retention_expires_at: datetime | None
    contract_reference: str | None
    summary: dict[str, Any]


class AdminJobDiagnostics(APIModel):
    job: JobResponse
    provider_versions: dict[str, Any]
    provider_metadata: dict[str, Any]
    total_provider_cost: float | None
    provider_cost_currency: str | None
    stage_timings: dict[str, Any]
    technical_error_detail: str | None
    assets: list[AssetResponse]
    model_runs: list[AdminModelRun]
    event_count: int
    low_confidence_event_count: int


class ProblemDetail(APIModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str
    request_id: str | None = None
