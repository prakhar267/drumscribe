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
    commercial_provider_license_confirmed: bool = False
    commercial_provider_approval_reference: str | None = None
    provider_timeout_seconds: float = Field(default=600, gt=0, le=3600)
    provider_poll_interval_seconds: float = Field(default=2, ge=0, le=30)
    yourmt3_command: str | None = None
    yourmt3_model_version: str = "YPTF.MoE+Multi-noPS"
    oaf_drums_command: str | None = None
    oaf_drums_model_version: str = "e-gmd-checkpoint"
    adtof_command: str | None = None
    adtof_model_version: str = "local-research"
    hybrid_command: str | None = None
    hybrid_model_version: str = "drumscribe-hybrid-v1"
    recall_fusion_command: str | None = None
    recall_fusion_model_version: str = "drumscribe-recall-fusion-v3"

    audioshake_api_url: str = "https://api.audioshake.ai"
    audioshake_api_key: SecretStr | None = None
    audioshake_contract_reference: str | None = None
    audioshake_separation_model: str = "drums"

    music_ai_api_url: str = "https://api.music.ai/v1"
    music_ai_api_key: SecretStr | None = None
    music_ai_contract_reference: str | None = None
    music_ai_separation_workflow: str | None = None
    music_ai_drum_result_key: str = "drums"

    klangio_api_url: str = "https://api.klang.io"
    klangio_api_key: SecretStr | None = None
    klangio_contract_reference: str | None = None

    storage_backend: Literal["s3", "local"] = "local"
    local_storage_path: Path = Path(".local-storage")
    s3_endpoint_url: str | None = None
    s3_public_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "drumscribe-private"
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_server_side_encryption: Literal["auto", "AES256", "none"] = "auto"
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
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    hsts_max_age_seconds: int = Field(default=31_536_000, ge=0)
    dev_expose_magic_link: bool = True
    magic_link_delivery: Literal["development", "resend", "webhook"] = "development"
    magic_link_webhook_url: str | None = None
    magic_link_webhook_secret: SecretStr | None = None
    resend_api_url: str = "https://api.resend.com"
    resend_api_key: SecretStr | None = None
    resend_from_email: str | None = None

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
    readiness_timeout_seconds: float = Field(default=10.0, gt=0, le=30)
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
            if not self.allowed_hosts or any(
                host in {"*", "localhost", "127.0.0.1", "testserver"} for host in self.allowed_hosts
            ):
                raise ValueError("production allowed hosts must be explicit public hostnames")
            if self.hsts_max_age_seconds < 31_536_000:
                raise ValueError("production HSTS must be at least one year")
            if not self.database_url.startswith(("postgresql+asyncpg://", "postgresql://")):
                raise ValueError("production requires PostgreSQL")
            if self.storage_backend != "s3":
                raise ValueError("production requires private S3-compatible storage")
            if self.queue_backend != "celery":
                raise ValueError("production requires the Celery queue backend")
            if self.pipeline_provider != "music_engine":
                raise ValueError("production cannot enable the deterministic development pipeline")
            if not self.commercial_provider_license_confirmed:
                raise ValueError("production providers require explicit commercial approval")
            if not self.commercial_provider_approval_reference:
                raise ValueError("production providers require an approval reference")
            transcription_provider = self.music_transcription_provider.casefold()
            separation_provider = self.source_separation_provider.casefold()
            beat_provider = self.beat_tracking_provider.casefold()
            owner_approved_provider_selected = (
                transcription_provider in {"adtof", "drumscribe_recall_fusion"}
                or separation_provider == "demucs"
                or beat_provider in {"research", "research_accurate"}
            )
            if (
                owner_approved_provider_selected
                and self.commercial_provider_approval_reference
                != "OWNER-ATTESTATION-2026-09-05"
            ):
                raise ValueError(
                    "self-hosted production providers require the pinned owner approval reference"
                )
            if transcription_provider not in {
                "klangio_drums",
                "adtof",
                "drumscribe_recall_fusion",
            }:
                raise ValueError("production requires an approved drum-transcription provider")
            if separation_provider not in {"audioshake", "music_ai", "demucs"}:
                raise ValueError("production requires an approved source-separation provider")
            if beat_provider not in {"klangio", "research", "research_accurate"}:
                raise ValueError("production requires an approved beat-tracking provider")
            if transcription_provider == "adtof" and not self.adtof_command:
                raise ValueError("production ADTOF command is missing")
            if (
                transcription_provider == "adtof"
                and self.adtof_model_version != "adtof-pytorch-85c192e78f71"
            ):
                raise ValueError("production ADTOF model version is not approved")
            if (
                transcription_provider == "drumscribe_recall_fusion"
                and not self.recall_fusion_command
            ):
                raise ValueError("production recall-fusion command is missing")
            if (
                transcription_provider == "drumscribe_recall_fusion"
                and self.recall_fusion_model_version != "drumscribe-recall-fusion-v3"
            ):
                raise ValueError("production recall-fusion model version is not approved")
            if (
                "klangio" in {transcription_provider, beat_provider}
                or transcription_provider == "klangio_drums"
            ) and (not self.klangio_api_key or not self.klangio_contract_reference):
                raise ValueError(
                    "production Klangio credentials and contract reference are missing"
                )
            if separation_provider == "audioshake" and (
                not self.audioshake_api_key or not self.audioshake_contract_reference
            ):
                raise ValueError(
                    "production AudioShake credentials and contract reference are missing"
                )
            if separation_provider == "music_ai" and (
                not self.music_ai_api_key
                or not self.music_ai_contract_reference
                or not self.music_ai_separation_workflow
            ):
                raise ValueError(
                    "production Music AI credentials, workflow and contract reference are missing"
                )
            if not self.cookie_secure:
                raise ValueError("production session cookies must be secure")
            if self.dev_expose_magic_link:
                raise ValueError("development magic-link delivery cannot be enabled in production")
            if self.magic_link_delivery == "webhook":
                if not self.magic_link_webhook_url:
                    raise ValueError("production magic-link webhook URL is missing")
            elif self.magic_link_delivery == "resend":
                if not self.resend_api_key or not self.resend_from_email:
                    raise ValueError("production Resend API key and sender are missing")
            else:
                raise ValueError("production requires Resend or webhook magic-link delivery")
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
