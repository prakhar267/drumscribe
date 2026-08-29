import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from drumscribe_api.enums import JOB_STAGE_PROGRESS, AssetKind, AssetStatus, JobStage
from drumscribe_api.errors import APIError
from drumscribe_api.models import AudioAsset, ProcessingJob, Project
from drumscribe_api.security import utcnow
from drumscribe_api.services.retention import RetentionService
from drumscribe_api.services.storage import LocalPrivateStorage
from drumscribe_api.tasks import celery_app, process_job_task

from .conftest import create_project, create_session, process_project, upload_wav, wav_bytes


def test_processing_worker_uses_acks_late_and_bounded_transient_retries() -> None:
    assert celery_app.conf.task_acks_late is True
    assert process_job_task.max_retries == 3


def test_retention_purges_expired_soft_deleted_project_media(
    client: TestClient, app, settings
) -> None:
    create_session(client)
    project = create_project(client)
    upload_wav(client, project["id"])
    assert process_project(client, app, project["id"])["stage"] == "READY"
    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 200
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404

    async def expire_assets() -> list[str]:
        async with app.state.database.session_factory() as db:
            assets = list(
                (
                    await db.execute(
                        select(AudioAsset).where(
                            AudioAsset.project_id == uuid.UUID(project["id"]),
                            AudioAsset.status == AssetStatus.DELETING,
                        )
                    )
                ).scalars()
            )
            assert assets
            for asset in assets:
                asset.expires_at = utcnow() - timedelta(seconds=1)
            await db.commit()
            return [asset.storage_key for asset in assets]

    assert client.portal is not None
    keys = client.portal.call(expire_assets)
    storage = app.state.storage
    assert isinstance(storage, LocalPrivateStorage)
    assert any(storage.path_for(key).exists() for key in keys)

    result = client.portal.call(
        RetentionService(settings, app.state.database, storage).run
    )
    assert result["assets"] == len(keys)
    assert all(not storage.path_for(key).exists() for key in keys)
    assert client.post(f"/api/v1/projects/{project['id']}/restore").status_code == 410


def test_retention_cleans_abandoned_pending_and_rejected_uploads(
    client: TestClient, app, settings
) -> None:
    create_session(client)
    project = create_project(client)
    pending = client.post(
        f"/api/v1/projects/{project['id']}/uploads/presign",
        json={
            "filename": "never-uploaded.wav",
            "contentType": "audio/wav",
            "sizeBytes": 44,
            "rightToUploadConfirmed": True,
        },
    ).json()
    invalid = b"RIFF\x10\x00\x00\x00WAVEnot-valid-audio"
    rejected = client.post(
        f"/api/v1/projects/{project['id']}/uploads/presign",
        json={
            "filename": "rejected.wav",
            "contentType": "audio/wav",
            "sizeBytes": len(invalid),
            "rightToUploadConfirmed": True,
        },
    ).json()
    assert client.put(
        rejected["uploadUrl"], content=invalid, headers=rejected["requiredHeaders"]
    ).status_code == 204
    assert client.post(
        f"/api/v1/uploads/{rejected['assetId']}/complete", json={}
    ).status_code == 200
    started = client.post(
        f"/api/v1/projects/{project['id']}/process",
        json={},
        headers={"Idempotency-Key": "reject-invalid-upload"},
    )
    assert started.status_code == 202
    assert client.portal is not None
    with pytest.raises(APIError):
        client.portal.call(app.state.pipeline.run, uuid.UUID(started.json()["id"]))

    async def expire_pending() -> None:
        async with app.state.database.session_factory() as db:
            asset = await db.get(AudioAsset, uuid.UUID(pending["assetId"]))
            assert asset is not None
            asset.expires_at = utcnow() - timedelta(seconds=1)
            await db.commit()

    client.portal.call(expire_pending)
    result = client.portal.call(
        RetentionService(settings, app.state.database, app.state.storage).run
    )
    assert result["assets"] == 2

    async def upload_statuses() -> list[AssetStatus]:
        async with app.state.database.session_factory() as db:
            assets = list(
                (
                    await db.execute(
                        select(AudioAsset).where(
                            AudioAsset.id.in_(
                                {
                                    uuid.UUID(pending["assetId"]),
                                    uuid.UUID(rejected["assetId"]),
                                }
                            )
                        )
                    )
                ).scalars()
            )
            return [asset.status for asset in assets]

    assert client.portal.call(upload_statuses) == [AssetStatus.DELETED, AssetStatus.DELETED]


def test_restore_never_revives_pipeline_deleted_history(client: TestClient, app) -> None:
    create_session(client)
    project = create_project(client)
    upload_wav(client, project["id"])
    process_project(client, app, project["id"])
    signed_before_delete = client.get(
        f"/api/v1/projects/{project['id']}/audio/original/url"
    ).json()["url"]
    assert client.get(signed_before_delete).status_code == 200
    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 200
    assert client.get(signed_before_delete).status_code == 404
    assert client.post(f"/api/v1/projects/{project['id']}/restore").status_code == 200

    async def statuses() -> list[tuple[AssetKind, AssetStatus]]:
        async with app.state.database.session_factory() as db:
            assets = list(
                (
                    await db.execute(
                        select(AudioAsset).where(
                            AudioAsset.project_id == uuid.UUID(project["id"])
                        )
                    )
                ).scalars()
            )
            return [(asset.kind, asset.status) for asset in assets]

    assert client.portal is not None
    rows = client.portal.call(statuses)
    assert any(
        kind == AssetKind.NORMALIZED
        and status in {AssetStatus.DELETING, AssetStatus.DELETED}
        for kind, status in rows
    )
    assert (AssetKind.ORIGINAL, AssetStatus.VERIFIED) in rows
    assert client.get(f"/api/v1/projects/{project['id']}/waveform/url").status_code == 200
    signed_after_restore = client.get(
        f"/api/v1/projects/{project['id']}/audio/original/url"
    ).json()["url"]
    assert signed_after_restore != signed_before_delete
    assert client.get(signed_after_restore).status_code == 200


def test_replacement_upload_scopes_idempotency_and_rebuilds_derived_audio(
    client: TestClient, app
) -> None:
    create_session(client)
    project = create_project(client)
    first_asset = upload_wav(client, project["id"], wav_bytes(1.0))
    first_job = process_project(client, app, project["id"])

    second_asset = upload_wav(client, project["id"], wav_bytes(1.25))
    second_job = process_project(client, app, project["id"])
    assert first_job["id"] != second_job["id"]
    assert second_job["stage"] == "READY"

    async def stem_state() -> tuple[str, list[AssetStatus]]:
        async with app.state.database.session_factory() as db:
            stems = list(
                (
                    await db.execute(
                        select(AudioAsset).where(
                            AudioAsset.project_id == uuid.UUID(project["id"]),
                            AudioAsset.kind == AssetKind.DRUM_STEM,
                        )
                    )
                ).scalars()
            )
            active = next(asset for asset in stems if asset.deleted_at is None)
            return active.storage_key, [asset.status for asset in stems]

    assert client.portal is not None
    active_key, stem_statuses = client.portal.call(stem_state)
    assert second_asset["id"] in active_key
    assert first_asset["id"] not in active_key
    assert AssetStatus.DELETING in stem_statuses


def test_worker_redelivery_reruns_the_committed_in_progress_stage(
    client: TestClient, app
) -> None:
    create_session(client)
    project = create_project(client)
    upload_wav(client, project["id"])
    started = client.post(
        f"/api/v1/projects/{project['id']}/process",
        json={},
        headers={"Idempotency-Key": "redelivery-checkpoint"},
    )
    job_id = uuid.UUID(started.json()["id"])

    async def emulate_worker_loss() -> None:
        async with app.state.database.session_factory() as db:
            job = await db.get(ProcessingJob, job_id)
            assert job is not None
            asset = await db.get(
                AudioAsset, uuid.UUID(str(job.provider_versions["inputAssetId"]))
            )
            assert asset is not None
            asset.status = AssetStatus.VERIFIED
            asset.codec = "pcm_s16le"
            asset.duration_seconds = 1
            project_row = await db.get(Project, uuid.UUID(project["id"]))
            assert project_row is not None
            project_row.duration_seconds = 1
            job.stage = JobStage.NORMALIZING
            job.last_completed_stage = JobStage.VALIDATING
            job.approximate_progress = JOB_STAGE_PROGRESS[JobStage.NORMALIZING]
            await db.commit()

    assert client.portal is not None
    client.portal.call(emulate_worker_loss)
    client.portal.call(app.state.pipeline.run, job_id)
    finished = client.get(f"/api/v1/jobs/{job_id}")
    assert finished.status_code == 200
    assert finished.json()["stage"] == "READY"
