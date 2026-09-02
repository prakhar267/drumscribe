import uuid
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient

from drumscribe_api.enums import EventSource, Instrument
from drumscribe_api.models import DrumEvent, Transcription
from drumscribe_api.services.exports import _music_engine_events
from drumscribe_api.services.pipeline import _quantize_hits_with_tempo, quantize_hits
from drumscribe_api.services.pipeline_contracts import RawDrumHit

from .conftest import (
    create_project,
    create_session,
    process_project,
    upload_wav,
)


def ready_project(client: TestClient, app):
    create_session(client)
    project = create_project(client)
    upload_wav(client, project["id"])
    job = process_project(client, app, project["id"])
    assert job["stage"] == "READY"
    assert job["approximateProgress"] == 100
    return project, job


def test_export_mapping_preserves_compound_meter_and_variable_tempo() -> None:
    for numerator, denominator in [(3, 4), (6, 8)]:
        transcription = Transcription(
            project_id=uuid.uuid4(),
            tempo_bpm=90,
            time_signature_numerator=numerator,
            time_signature_denominator=denominator,
            tempo_map=[
                {"kind": "tempo", "startBeat": "0", "bpm": 90, "confidence": 0.9},
                {"kind": "tempo", "startBeat": "6", "bpm": 110, "confidence": 0.8},
                {
                    "kind": "timeSignature",
                    "startBeat": "0",
                    "numerator": numerator,
                    "denominator": denominator,
                    "confidence": 0.95,
                },
            ],
        )
        event = DrumEvent(
            transcription_id=uuid.uuid4(),
            project_id=transcription.project_id,
            instrument=Instrument.KICK,
            onset_seconds=2,
            duration_seconds=0.08,
            velocity=100,
            confidence=0.9,
            source=EventSource.AI,
            beat_position=0,
            measure_index=1,
            subdivision="1/16",
            quantized_onset=2,
            manually_edited=False,
        )
        converted, _, tempo_map = _music_engine_events([event], transcription)
        assert converted[0].beat_position == Fraction(3)
        assert len(tempo_map.changes) == 2
        assert tempo_map.time_signatures[0].numerator == numerator


def test_pipeline_quantization_preserves_offset_and_variable_tempo_map() -> None:
    analysis = {
        "tempoBpm": 90,
        "timeSignatureNumerator": 4,
        "timeSignatureDenominator": 4,
        "confidence": 0.9,
        "offsetSeconds": 0.25,
        "tempoMap": [
            {"startBeat": "0", "bpm": 120, "confidence": 0.9},
            {"startBeat": "2", "bpm": 60, "confidence": 0.9},
        ],
        "timeSignatures": [
            {
                "startBeat": "0",
                "numerator": 4,
                "denominator": 4,
                "confidence": 0.9,
            }
        ],
    }
    event = quantize_hits(
        [RawDrumHit(Instrument.SNARE, 2.26, 110, 0.95)],
        timing_analysis=analysis,
    )[0]
    assert event["onset_seconds"] == 2.26
    assert event["quantized_onset"] == 2.25
    assert event["measure_index"] == 0
    assert event["beat_position"] == 3


def test_pipeline_quantization_rehydrates_timestamped_commercial_beats() -> None:
    analysis = {
        "tempoBpm": 120,
        "timeSignatureNumerator": 4,
        "timeSignatureDenominator": 4,
        "beats": [
            {"timeSeconds": 0.2, "confidence": 0.95},
            {"timeSeconds": 0.7, "confidence": 0.95},
            {"timeSeconds": 1.3, "confidence": 0.95},
            {"timeSeconds": 1.8, "confidence": 0.95},
        ],
    }
    event = quantize_hits(
        [RawDrumHit(Instrument.KICK, 1.29, 100, 0.9)],
        timing_analysis=analysis,
    )[0]
    assert event["quantized_onset"] == 1.3
    assert event["beat_position"] == 2


def test_pipeline_rhythm_completion_is_explicitly_gated() -> None:
    analysis = {
        "tempoBpm": 120,
        "timeSignatureNumerator": 4,
        "timeSignatureDenominator": 4,
        "offsetSeconds": 0.30,
    }
    hits = [
        *[
            RawDrumHit(Instrument.KICK, 0.24 + index * 0.125, 100, 0.95)
            for index in (0, 8, 16, 24, 32, 40)
        ],
        *[
            RawDrumHit(Instrument.CLOSED_HIHAT, 0.24 + index * 0.125, 80, 0.9)
            for index in (0, 4, 8, 16, 20, 28, 32, 36, 40)
        ],
    ]

    baseline = quantize_hits(hits, timing_analysis=analysis)
    completed, completed_tempo, applied = _quantize_hits_with_tempo(
        hits,
        timing_analysis=analysis,
        rhythm_completion=True,
    )

    assert len(baseline) == len(hits)
    assert len(completed) > len(baseline)
    assert applied is True
    assert completed_tempo.offset_seconds == pytest.approx(0.24836880645161298)
    assert completed[0]["quantized_onset"] == pytest.approx(0.24836880645161298)


def test_idempotent_processing_and_durable_stage_progress(client: TestClient, app) -> None:
    project, job = ready_project(client, app)
    repeated = client.post(
        f"/api/v1/projects/{project['id']}/process",
        json={},
        headers={"Idempotency-Key": f"process-{project['id']}"},
    )
    assert repeated.status_code == 202
    assert repeated.json()["id"] == job["id"]
    assert repeated.json()["progressIsApproximate"] is True


def test_cancel_and_retry_job_state_machine(client: TestClient) -> None:
    create_session(client)
    project = create_project(client)
    upload_wav(client, project["id"])
    started = client.post(
        f"/api/v1/projects/{project['id']}/process",
        json={},
        headers={"Idempotency-Key": "cancel-me"},
    )
    job_id = started.json()["id"]
    cancelled = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["stage"] == "CANCELLED"
    retried = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert retried.status_code == 202
    assert retried.json()["stage"] == "RECEIVED"
    assert retried.json()["retryCount"] == 1


def test_bulk_edit_version_conflict_and_revision_restore(client: TestClient, app) -> None:
    project, _ = ready_project(client, app)
    events_response = client.get(f"/api/v1/projects/{project['id']}/events")
    assert events_response.status_code == 200
    original = events_response.json()
    assert len(original["items"]) >= 4
    first = original["items"][0]

    edit = client.patch(
        f"/api/v1/projects/{project['id']}/events/bulk",
        json={
            "deleteIds": [first["id"]],
            "upserts": [
                {
                    "instrument": "SNARE",
                    "onsetSeconds": 0.375,
                    "durationSeconds": 0.08,
                    "velocity": 101,
                    "confidence": None,
                    "source": "USER",
                    "beatPosition": 0.75,
                    "measureIndex": 0,
                    "subdivision": "1/16",
                    "quantizedOnset": 0.375,
                }
            ],
            "expectedVersion": original["version"],
            "revisionLabel": "Fix opening hit",
        },
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["version"] == original["version"] + 1

    stale = client.patch(
        f"/api/v1/projects/{project['id']}/events/bulk",
        json={
            "deleteIds": [edit.json()["upserted"][0]["id"]],
            "expectedVersion": original["version"],
            "revisionLabel": "stale",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "EDIT_VERSION_CONFLICT"

    revisions = client.get(f"/api/v1/projects/{project['id']}/revisions").json()["items"]
    ai_original = next(item for item in revisions if item["kind"] == "AI_ORIGINAL")
    restored = client.post(
        f"/api/v1/projects/{project['id']}/revisions/{ai_original['id']}/restore"
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["eventCount"] == len(original["items"])


def test_unchanged_full_chart_upsert_preserves_ai_provenance(client: TestClient, app) -> None:
    project, _ = ready_project(client, app)
    original = client.get(f"/api/v1/projects/{project['id']}/events").json()
    revision_count = len(client.get(f"/api/v1/projects/{project['id']}/revisions").json()["items"])
    fields = {
        "id",
        "instrument",
        "onsetSeconds",
        "durationSeconds",
        "velocity",
        "confidence",
        "source",
        "beatPosition",
        "measureIndex",
        "subdivision",
        "quantizedOnset",
    }
    unchanged = [
        {key: value for key, value in event.items() if key in fields} for event in original["items"]
    ]
    response = client.patch(
        f"/api/v1/projects/{project['id']}/events/bulk",
        json={
            "upserts": unchanged,
            "expectedVersion": original["version"],
            "revisionLabel": "No-op full chart save",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["version"] == original["version"]
    assert response.json()["upserted"] == []
    assert response.json()["revisionId"] is None
    assert (
        len(client.get(f"/api/v1/projects/{project['id']}/revisions").json()["items"])
        == revision_count
    )

    first = dict(unchanged[0])
    original_confidence = first["confidence"]
    first.pop("confidence")
    first["velocity"] = min(127, int(first["velocity"]) + 1)
    changed = client.patch(
        f"/api/v1/projects/{project['id']}/events/bulk",
        json={
            "upserts": [first],
            "expectedVersion": original["version"],
            "revisionLabel": "One real correction",
        },
    )
    assert changed.status_code == 200, changed.text
    event = changed.json()["upserted"][0]
    assert event["source"] == "USER"
    assert event["manuallyEdited"] is True
    assert event["confidence"] == original_confidence


def test_all_exports_use_latest_events_and_private_signed_urls(client: TestClient, app) -> None:
    project, _ = ready_project(client, app)
    signatures = {"MIDI": b"MThd", "MUSICXML": b"<?xml", "PDF": b"%PDF"}
    for export_format, magic in signatures.items():
        requested = client.post(
            f"/api/v1/projects/{project['id']}/exports",
            json={"format": export_format},
            headers={"Idempotency-Key": f"{project['id']}-{export_format}"},
        )
        assert requested.status_code == 202, requested.text
        export_id = uuid.UUID(requested.json()["id"])
        assert client.portal is not None
        client.portal.call(app.state.export_service.run, export_id)
        status_response = client.get(f"/api/v1/exports/{export_id}")
        assert status_response.json()["status"] == "READY", status_response.text
        download = client.get(f"/api/v1/exports/{export_id}/download")
        assert download.status_code == 200
        file_response = client.get(download.json()["url"])
        assert file_response.status_code == 200
        assert file_response.content.startswith(magic)


def test_audio_urls_are_owner_scoped(client: TestClient, app) -> None:
    project, job = ready_project(client, app)
    token_a = client.cookies.get("drumscribe_session")
    assert token_a
    waveform = client.get(f"/api/v1/projects/{project['id']}/waveform/url")
    assert waveform.status_code == 200
    envelope = client.get(waveform.json()["url"])
    assert envelope.status_code == 200
    assert "peaks" in envelope.json()
    assert client.get(f"/api/v1/admin/jobs/{job['id']}").status_code == 403
    client.cookies.clear()
    token_b = create_session(client)
    denied = client.get(
        f"/api/v1/projects/{project['id']}/audio/original/url",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert denied.status_code == 404
    allowed = client.get(
        f"/api/v1/projects/{project['id']}/audio/original/url",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert allowed.status_code == 200
