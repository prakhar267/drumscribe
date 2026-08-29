import importlib
import uuid
from datetime import timedelta
from fractions import Fraction
from typing import Any, cast

import structlog
from sqlalchemy import select

from ..config import Settings
from ..database import Database
from ..enums import ExportFormat, ExportStatus
from ..errors import APIError
from ..models import DrumEvent, Export, Project, Transcription
from ..security import utcnow
from .storage import PrivateStorage

logger = structlog.get_logger(__name__)

EXPORT_CONTENT_TYPES: dict[ExportFormat, tuple[str, str]] = {
    ExportFormat.MIDI: ("audio/midi", "mid"),
    ExportFormat.MUSICXML: ("application/vnd.recordare.musicxml+xml", "musicxml"),
    ExportFormat.PDF: ("application/pdf", "pdf"),
}


async def create_or_get_export(
    db: Any,
    *,
    project: Project,
    transcription: Transcription,
    export_format: ExportFormat,
    idempotency_key: str,
) -> tuple[Export, bool]:
    existing = (
        await db.execute(
            select(Export).where(
                Export.project_id == project.id,
                Export.idempotency_key == idempotency_key,
                Export.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.format != export_format or existing.transcription_id != transcription.id:
            raise APIError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "This idempotency key was already used for a different export request.",
            )
        return existing, False
    export = Export(
        project_id=project.id,
        transcription_id=transcription.id,
        format=export_format,
        status=ExportStatus.QUEUED,
        idempotency_key=idempotency_key,
    )
    db.add(export)
    await db.flush()
    return export, True


def _music_engine_tempo_map(transcription: Transcription, engine: Any) -> Any:
    changes: list[Any] = []
    signatures: list[Any] = []
    offset_seconds = 0.0
    for item in transcription.tempo_map or []:
        kind = item.get("kind")
        if kind == "offset":
            offset_seconds = float(item.get("offsetSeconds", 0))
        elif kind == "timeSignature" or ("numerator" in item and "denominator" in item):
            signatures.append(
                engine.TimeSignature(
                    int(item["numerator"]),
                    int(item["denominator"]),
                    item.get("startBeat", 0),
                    float(item.get("confidence", 1)),
                )
            )
        elif "bpm" in item:
            changes.append(
                engine.TempoChange(
                    item.get("startBeat", 0),
                    float(item["bpm"]),
                    float(item.get("confidence", 1)),
                )
            )
    if not changes:
        changes = [engine.TempoChange(0, transcription.tempo_bpm)]
    if not signatures:
        signatures = [
            engine.TimeSignature(
                transcription.time_signature_numerator,
                transcription.time_signature_denominator,
            )
        ]
    return engine.TempoMap(tuple(changes), tuple(signatures), offset_seconds)


def _music_engine_events(
    events: list[DrumEvent], transcription: Transcription
) -> tuple[list[Any], Any, Any]:
    engine = importlib.import_module("drumscribe_music")
    tempo_map = _music_engine_tempo_map(transcription, engine)
    subdivision_map = {
        "1/4": engine.GridSubdivision.QUARTER,
        "1/8": engine.GridSubdivision.EIGHTH,
        "1/16": engine.GridSubdivision.SIXTEENTH,
        "1/32": engine.GridSubdivision.THIRTY_SECOND,
        "1/8T": engine.GridSubdivision.EIGHTH_TRIPLET,
        "1/16T": engine.GridSubdivision.SIXTEENTH_TRIPLET,
    }
    converted: list[Any] = []
    for event in events:
        absolute_beat = tempo_map.position_to_beat(
            event.measure_index,
            Fraction(str(event.beat_position)).limit_denominator(960),
        ).limit_denominator(960)
        converted.append(
            engine.DrumEvent(
                id=str(event.id),
                project_id=str(event.project_id),
                instrument=engine.Instrument(event.instrument.value),
                onset_seconds=event.onset_seconds,
                duration_seconds=event.duration_seconds,
                velocity=event.velocity,
                confidence=event.confidence if event.confidence is not None else 0.5,
                source=(
                    engine.EventSource.MANUAL
                    if event.manually_edited
                    else engine.EventSource.TRANSCRIPTION
                ),
                beat_position=absolute_beat,
                measure_index=event.measure_index,
                beat_in_measure=Fraction(str(event.beat_position)).limit_denominator(960),
                subdivision=subdivision_map.get(event.subdivision),
                quantized_onset_seconds=event.quantized_onset,
                manually_edited=event.manually_edited,
            )
        )
    return converted, engine, tempo_map


def generate_export_bytes(
    export_format: ExportFormat,
    events: list[DrumEvent],
    transcription: Transcription,
    project: Project,
) -> bytes:
    converted, engine, tempo_map = _music_engine_events(events, transcription)
    if export_format == ExportFormat.MIDI:
        return cast(bytes, engine.generate_midi(converted, tempo_map))
    if export_format == ExportFormat.MUSICXML:
        return cast(
            bytes,
            engine.generate_musicxml(
                converted,
                tempo_map,
                title=project.title,
                artist=project.artist,
            ),
        )
    return cast(
        bytes,
        engine.generate_pdf(
            converted,
            tempo_map,
            title=project.title,
            artist=project.artist,
        ),
    )


class ExportService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        storage: PrivateStorage,
    ) -> None:
        self.settings = settings
        self.database = database
        self.storage = storage

    async def run(self, export_id: uuid.UUID) -> None:
        async with self.database.session_factory() as db:
            export = await db.get(Export, export_id)
            if export is None or export.deleted_at is not None:
                return
            if export.status == ExportStatus.READY:
                return
            export.status = ExportStatus.GENERATING
            await db.commit()
            try:
                project = await db.get(Project, export.project_id)
                transcription = await db.get(Transcription, export.transcription_id)
                if project is None or project.deleted_at is not None or transcription is None:
                    raise RuntimeError("export source is unavailable")
                events = list(
                    (
                        await db.execute(
                            select(DrumEvent)
                            .where(
                                DrumEvent.transcription_id == transcription.id,
                                DrumEvent.deleted_at.is_(None),
                            )
                            .order_by(DrumEvent.quantized_onset, DrumEvent.id)
                        )
                    ).scalars()
                )
                data = generate_export_bytes(export.format, events, transcription, project)
                content_type, extension = EXPORT_CONTENT_TYPES[export.format]
                key = (
                    f"users/{project.owner_id}/projects/{project.id}/exports/"
                    f"{export.id}.{extension}"
                )
                await self.storage.put_bytes(key, data, content_type)
                export.storage_key = key
                export.status = ExportStatus.READY
                export.finished_at = utcnow()
                export.expires_at = utcnow() + timedelta(hours=self.settings.export_retention_hours)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                export = await db.get(Export, export_id)
                if export:
                    export.status = ExportStatus.FAILED
                    export.error_detail = f"{type(exc).__name__}: {str(exc)[:1000]}"
                    export.finished_at = utcnow()
                    await db.commit()
                logger.exception("export_failed", export_id=str(export_id))
                raise
