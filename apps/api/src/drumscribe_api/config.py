from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .enums import Environment


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DRUMSCRIBE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DrumScribe API"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./drumscribe.db"
    redis_url: str = "redis://localhost:6379/0"
    queue_backend: Literal["celery", "inline", "none"] = "inline"
    pipeline_provider: Literal["development", "music_engine"] = "development"
    source_separation_provider: str = "passthrough"
    music_transcription_provider: str = "mock"
    beat_tracking_provider: str = "mock"

    storage_backend: Literal["s3", "local"] = "local"
    local_storage_path: Path = Path(".local-storage")
    s3_endpoint_url: str | None = None
    s3_public_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "drumscribe-private"
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_configure_bucket_cors: bool = False

    session_secret: SecretStr = SecretStr("development-only-change-this-secret")
    session_cookie_name: str = "drumscribe_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 30
    magic_link_ttl_seconds: int = 60 * 15
    signed_url_ttl_seconds: int = 60 * 10
    cookie_secure: bool = False
    cookie_domain: str | None = None
    public_api_url: str = "http://localhost:8000"
    web_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    dev_expose_magic_link: bool = True
    magic_link_delivery: Literal["development", "webhook"] = "development"
    magic_link_webhook_url: str | None = None
    magic_link_webhook_secret: SecretStr | None = None

    max_upload_bytes: int = 150 * 1024 * 1024
    max_audio_duration_seconds: float = 12 * 60
    anonymous_max_audio_duration_seconds: float = 90
    max_bulk_events: int = 5_000
    max_concurrent_jobs_per_user: int = 2
    max_concurrent_jobs_anonymous: int = 1
    ffprobe_binary: str = "ffprobe"
    ffmpeg_binary: str = "ffmpeg"
    rate_limit_per_minute: int = Field(default=180, gt=0)
    auth_rate_limit_per_minute: int = Field(default=10, gt=0)
    enable_rate_limiting: bool = True
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    anonymous_retention_hours: int = 24
    export_retention_hours: int = 24 * 7
    project_delete_grace_hours: int = 24 * 7
    replaced_upload_retention_hours: int = 24
    unprocessed_upload_retention_hours: int = 24
    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0, le=1)

    triplet_quantization: bool = False
    advanced_cymbal_classification: bool = False
    variable_tempo: bool = False
    practice_mode: bool = True
    model_confidence_overlay: bool = True
    auto_create_schema: bool = False

    @model_validator(mode="after")
    def validate_deployment_safety(self) -> "Settings":
        if (
            self.max_upload_bytes <= 0
            or self.max_audio_duration_seconds <= 0
            or self.anonymous_max_audio_duration_seconds <= 0
        ):
            raise ValueError("upload limits must be positive")
        if self.environment is Environment.PRODUCTION:
            if any(origin == "*" for origin in self.web_origins):
                raise ValueError("production CORS origins must be explicit")
            if not self.database_url.startswith(("postgresql+asyncpg://", "postgresql://")):
                raise ValueError("production requires PostgreSQL")
            if self.storage_backend != "s3":
                raise ValueError("production requires private S3-compatible storage")
            if self.queue_backend != "celery":
                raise ValueError("production requires the Celery queue backend")
            if self.pipeline_provider != "music_engine":
                raise ValueError("production cannot enable the deterministic development pipeline")
            if self.music_transcription_provider.casefold() in {"mock", "research"}:
                raise ValueError(
                    "production requires a commercially approved transcription provider"
                )
            if self.source_separation_provider.casefold() in {"passthrough", "demucs"}:
                raise ValueError(
                    "production requires a commercially approved source-separation provider"
                )
            if self.beat_tracking_provider.casefold() in {"mock", "research"}:
                raise ValueError("production requires a commercially approved beat tracker")
            if not self.cookie_secure:
                raise ValueError("production session cookies must be secure")
            if self.dev_expose_magic_link:
                raise ValueError("development magic-link delivery cannot be enabled in production")
            if self.magic_link_delivery != "webhook" or not self.magic_link_webhook_url:
                raise ValueError("production requires a configured magic-link delivery webhook")
            secret = self.session_secret.get_secret_value()
            if len(secret) < 32 or secret == "development-only-change-this-secret":
                raise ValueError("production requires a strong SESSION_SECRET")
            if not self.s3_access_key_id or not self.s3_secret_access_key:
                raise ValueError("production S3 credentials are missing")
            if self.s3_endpoint_url and not self.s3_public_endpoint_url:
                raise ValueError(
                    "custom production S3 endpoints require a browser-reachable public endpoint"
                )
        return self

    @property
    def session_secret_bytes(self) -> bytes:
        return self.session_secret.get_secret_value().encode("utf-8")

    @property
    def feature_flags(self) -> dict[str, bool]:
        return {
            "tripletQuantization": self.triplet_quantization,
            "advancedCymbalClassification": self.advanced_cymbal_classification,
            "variableTempo": self.variable_tempo,
            "practiceMode": self.practice_mode,
            "modelConfidenceOverlay": self.model_confidence_overlay,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
