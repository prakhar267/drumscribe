import contextlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import delete, select

from drumscribe_api.enums import AssetKind, JobStage
from drumscribe_api.models import AudioAsset, ModelRun, ProcessingJob, Project
from drumscribe_api.services.pipeline_contracts import (
    DrumTranscriptionResult,
    ProviderCategory,
    ProviderRunMetadata,
)
from drumscribe_api.services.storage import LocalPrivateStorage

from .conftest import create_project, create_session, process_project, upload_wav


class SamePathTranscriber:
    def __init__(self) -> None:
        self.paths: tuple[Path, Path | None] | None = None

    def transcription_input_kind(self) -> str:
        return "full_mix"

    async def transcribe(
        self,
        audio_path: Path,
        duration: float,
        *,
        mixture_path: Path | None = None,
    ) -> DrumTranscriptionResult:
        del duration
        self.paths = (audio_path, mixture_path)
        return DrumTranscriptionResult(
            hits=(),
            metadata=ProviderRunMetadata(
                provider="same-path-test",
                category=ProviderCategory.TEST_FIXTURE,
                model_version="1",
                request_id=None,
                processing_ms=0,
            ),
        )


def test_full_mix_recall_fusion_downloads_normalized_audio_once(client, app, monkeypatch) -> None:
    create_session(client)
    project_payload = create_project(client)
    upload_wav(client, project_payload["id"])
    completed = process_project(client, app, project_payload["id"])
    job_id = uuid.UUID(completed["id"])
    project_id = uuid.UUID(project_payload["id"])

    storage = app.state.storage
    assert isinstance(storage, LocalPrivateStorage)
    original_materialize = storage.materialize
    materialized: list[str] = []

    @contextlib.asynccontextmanager
    async def counting_materialize(key: str) -> AsyncIterator[Path]:
        materialized.append(key)
        async with original_materialize(key) as path:
            yield path

    monkeypatch.setattr(storage, "materialize", counting_materialize)
    transcriber = SamePathTranscriber()
    monkeypatch.setattr(app.state.pipeline, "music", transcriber)
    app.state.pipeline.settings.music_transcription_provider = "drumscribe_recall_fusion"

    async def rerun_transcription() -> str:
        async with app.state.database.session_factory() as db:
            await db.execute(delete(ModelRun).where(ModelRun.job_id == job_id))
            job = await db.get(ProcessingJob, job_id)
            project = await db.get(Project, project_id)
            assert job is not None and project is not None
            normalized = (
                await db.execute(
                    select(AudioAsset).where(
                        AudioAsset.project_id == project_id,
                        AudioAsset.kind == AssetKind.NORMALIZED,
                    )
                )
            ).scalar_one()
            normalized.deleted_at = None
            normalized.expires_at = None
            normalized_key = normalized.storage_key
            await db.flush()
            await app.state.pipeline._run_stage(db, job, project, JobStage.TRANSCRIBING)
            await db.commit()
            return normalized_key

    assert client.portal is not None
    normalized_key = client.portal.call(rerun_transcription)

    assert materialized == [normalized_key]
    assert transcriber.paths is not None
    assert transcriber.paths[0] == transcriber.paths[1]
