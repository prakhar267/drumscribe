import uuid

from sqlalchemy import select

from drumscribe_api.enums import JobStage
from drumscribe_api.models import ProcessingJob, Project
from drumscribe_api.worker_recovery import recover_interrupted_jobs

from .conftest import create_project, create_session, upload_wav


class CapturingQueue:
    def __init__(self) -> None:
        self.processing: list[uuid.UUID] = []

    async def enqueue_processing(self, job_id: uuid.UUID) -> None:
        self.processing.append(job_id)

    async def enqueue_export(self, export_id: uuid.UUID) -> None:
        del export_id

    async def healthcheck(self) -> None:
        return

    async def close(self) -> None:
        return


def test_worker_start_requeues_only_started_active_projects(client, app) -> None:
    create_session(client)
    interrupted_project = create_project(client, title="Interrupted")
    upload_wav(client, interrupted_project["id"])
    interrupted = client.post(
        f"/api/v1/projects/{interrupted_project['id']}/process",
        json={},
        headers={"Idempotency-Key": "interrupted"},
    ).json()

    client.cookies.clear()
    create_session(client)
    received_project = create_project(client, title="Still queued")
    upload_wav(client, received_project["id"])
    received = client.post(
        f"/api/v1/projects/{received_project['id']}/process",
        json={},
        headers={"Idempotency-Key": "received"},
    ).json()

    client.cookies.clear()
    create_session(client)
    deleted_project = create_project(client, title="Deleted")
    upload_wav(client, deleted_project["id"])
    deleted = client.post(
        f"/api/v1/projects/{deleted_project['id']}/process",
        json={},
        headers={"Idempotency-Key": "deleted"},
    ).json()

    async def arrange() -> None:
        async with app.state.database.session_factory() as db:
            for job_id in (interrupted["id"], deleted["id"]):
                job = await db.get(ProcessingJob, uuid.UUID(job_id))
                assert job is not None
                job.stage = JobStage.NORMALIZING
            project = await db.get(Project, uuid.UUID(deleted_project["id"]))
            assert project is not None
            project.deleted_at = project.updated_at
            await db.commit()

    assert client.portal is not None
    client.portal.call(arrange)
    queue = CapturingQueue()
    recovered = client.portal.call(recover_interrupted_jobs, app.state.database, queue)

    assert recovered == (uuid.UUID(interrupted["id"]),)
    assert queue.processing == [uuid.UUID(interrupted["id"])]

    async def stages() -> dict[uuid.UUID, JobStage]:
        async with app.state.database.session_factory() as db:
            rows = (
                await db.execute(
                    select(ProcessingJob.id, ProcessingJob.stage).where(
                        ProcessingJob.id.in_(
                            {
                                uuid.UUID(interrupted["id"]),
                                uuid.UUID(received["id"]),
                                uuid.UUID(deleted["id"]),
                            }
                        )
                    )
                )
            ).all()
            return dict(rows)

    assert client.portal.call(stages) == {
        uuid.UUID(interrupted["id"]): JobStage.NORMALIZING,
        uuid.UUID(received["id"]): JobStage.RECEIVED,
        uuid.UUID(deleted["id"]): JobStage.NORMALIZING,
    }
