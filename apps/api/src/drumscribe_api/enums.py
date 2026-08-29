from enum import StrEnum


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class UserRole(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class UserKind(StrEnum):
    ANONYMOUS = "ANONYMOUS"
    REGISTERED = "REGISTERED"


class Entitlement(StrEnum):
    FREE_BETA = "FREE_BETA"


class ProjectStatus(StrEnum):
    DRAFT = "DRAFT"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AssetKind(StrEnum):
    ORIGINAL = "ORIGINAL"
    NORMALIZED = "NORMALIZED"
    DRUM_STEM = "DRUM_STEM"
    WAVEFORM_PEAKS = "WAVEFORM_PEAKS"
    SCORE_SOURCE = "SCORE_SOURCE"
    EXPORT = "EXPORT"


class AssetStatus(StrEnum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    UPLOADED = "UPLOADED"
    VERIFIED = "VERIFIED"
    DELETING = "DELETING"
    DELETED = "DELETED"
    REJECTED = "REJECTED"


class JobStage(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    NORMALIZING = "NORMALIZING"
    SEPARATING_DRUMS = "SEPARATING_DRUMS"
    TRANSCRIBING = "TRANSCRIBING"
    DETECTING_BEATS = "DETECTING_BEATS"
    QUANTIZING = "QUANTIZING"
    GENERATING_SCORE = "GENERATING_SCORE"
    FINALIZING = "FINALIZING"
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobErrorCode(StrEnum):
    INVALID_AUDIO = "INVALID_AUDIO"
    UNSUPPORTED_CODEC = "UNSUPPORTED_CODEC"
    AUDIO_TOO_LONG = "AUDIO_TOO_LONG"
    AUDIO_TOO_LARGE = "AUDIO_TOO_LARGE"
    SEPARATION_FAILED = "SEPARATION_FAILED"
    TRANSCRIPTION_FAILED = "TRANSCRIPTION_FAILED"
    BEAT_TRACKING_FAILED = "BEAT_TRACKING_FAILED"
    SCORE_GENERATION_FAILED = "SCORE_GENERATION_FAILED"
    WORKER_TIMEOUT = "WORKER_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ExportFormat(StrEnum):
    MIDI = "MIDI"
    MUSICXML = "MUSICXML"
    PDF = "PDF"


class ExportStatus(StrEnum):
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RevisionKind(StrEnum):
    AI_ORIGINAL = "AI_ORIGINAL"
    AUTOSAVE = "AUTOSAVE"
    MANUAL = "MANUAL"
    RESTORE = "RESTORE"


class EventSource(StrEnum):
    AI = "AI"
    USER = "USER"
    IMPORT = "IMPORT"


class Instrument(StrEnum):
    KICK = "KICK"
    SNARE = "SNARE"
    CROSS_STICK = "CROSS_STICK"
    CLOSED_HIHAT = "CLOSED_HIHAT"
    OPEN_HIHAT = "OPEN_HIHAT"
    PEDAL_HIHAT = "PEDAL_HIHAT"
    RIDE = "RIDE"
    RIDE_BELL = "RIDE_BELL"
    CRASH = "CRASH"
    HIGH_TOM = "HIGH_TOM"
    MID_TOM = "MID_TOM"
    LOW_TOM = "LOW_TOM"
    FLOOR_TOM = "FLOOR_TOM"


TERMINAL_JOB_STAGES = {JobStage.READY, JobStage.FAILED, JobStage.CANCELLED}

JOB_STAGE_PROGRESS: dict[JobStage, int] = {
    JobStage.RECEIVED: 0,
    JobStage.VALIDATING: 5,
    JobStage.NORMALIZING: 12,
    JobStage.SEPARATING_DRUMS: 25,
    JobStage.TRANSCRIBING: 52,
    JobStage.DETECTING_BEATS: 68,
    JobStage.QUANTIZING: 78,
    JobStage.GENERATING_SCORE: 88,
    JobStage.FINALIZING: 96,
    JobStage.READY: 100,
    JobStage.FAILED: 100,
    JobStage.CANCELLED: 100,
}

FRIENDLY_JOB_STAGES: dict[JobStage, str] = {
    JobStage.RECEIVED: "Preparing audio",
    JobStage.VALIDATING: "Preparing audio",
    JobStage.NORMALIZING: "Preparing audio",
    JobStage.SEPARATING_DRUMS: "Isolating drums",
    JobStage.TRANSCRIBING: "Listening for drum hits",
    JobStage.DETECTING_BEATS: "Building the rhythm",
    JobStage.QUANTIZING: "Building the rhythm",
    JobStage.GENERATING_SCORE: "Creating your chart",
    JobStage.FINALIZING: "Almost ready",
    JobStage.READY: "Your chart is ready",
    JobStage.FAILED: "Processing could not be completed",
    JobStage.CANCELLED: "Processing cancelled",
}

