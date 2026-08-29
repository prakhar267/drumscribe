from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import create_project, create_session, process_project, upload_wav


def ready_project(client: TestClient, app):
    create_session(client)
    project = create_project(client)
    upload_wav(client, project["id"])
    assert process_project(client, app, project["id"])["stage"] == "READY"
    return project


def event_write(event: dict, **changes: object) -> dict:
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
    payload = {key: value for key, value in event.items() if key in fields}
    payload.update(changes)
    return payload


def shifted_timing_payload(expected_version: int) -> dict:
    beats = []
    for index in range(9):
        beat_in_measure = index % 4 + 1
        beats.append(
            {
                "timeSeconds": round(0.1 + index * 0.5, 6),
                "beatInMeasure": beat_in_measure,
                "measureIndex": index // 4,
                "isDownbeat": beat_in_measure == 1,
                "confidence": None,
            }
        )
    return {
        "expectedVersion": expected_version,
        "barOneSeconds": 0.1,
        "segments": [
            {
                "startSeconds": 0.1,
                "bpm": 120,
                "timeSignatureNumerator": 4,
                "timeSignatureDenominator": 4,
                "startMeasure": 0,
            }
        ],
        "beats": beats,
        "requantize": "all",
        "preserveManualEdits": True,
    }


def test_timing_update_preserves_raw_onsets_and_manual_event_mapping(
    client: TestClient, app
) -> None:
    project = ready_project(client, app)
    project_id = project["id"]
    timing = client.get(f"/api/v1/projects/{project_id}/timing")
    assert timing.status_code == 200, timing.text
    initial_timing = timing.json()
    assert initial_timing["source"] == "AI"
    assert len(initial_timing["beats"]) >= 2

    original_events_response = client.get(f"/api/v1/projects/{project_id}/events")
    original = original_events_response.json()
    first = original["items"][0]
    manual_edit = client.patch(
        f"/api/v1/projects/{project_id}/events/bulk",
        json={
            "upserts": [event_write(first, velocity=min(127, first["velocity"] + 1))],
            "expectedVersion": original["version"],
            "revisionLabel": "Manual hit before timing correction",
        },
    )
    assert manual_edit.status_code == 200, manual_edit.text
    manually_mapped_onset = manual_edit.json()["upserted"][0]["quantizedOnset"]

    before = client.get(f"/api/v1/projects/{project_id}/events").json()["items"]
    raw_onsets_before = {event["id"]: event["onsetSeconds"] for event in before}
    quantized_before = {event["id"]: event["quantizedOnset"] for event in before}
    updated = client.patch(
        f"/api/v1/projects/{project_id}/timing",
        json=shifted_timing_payload(initial_timing["timingVersion"]),
    )
    assert updated.status_code == 200, updated.text
    result = updated.json()
    assert result["source"] == "MANUAL"
    assert result["barOneSeconds"] == 0.1
    assert result["requantizedEventCount"] == len(before) - 1

    after = client.get(f"/api/v1/projects/{project_id}/events").json()["items"]
    assert {event["id"]: event["onsetSeconds"] for event in after} == raw_onsets_before
    after_by_id = {event["id"]: event for event in after}
    assert after_by_id[first["id"]]["quantizedOnset"] == manually_mapped_onset
    assert any(
        event["quantizedOnset"] != quantized_before[event["id"]]
        for event in after
        if event["id"] != first["id"]
    )

    stale = client.patch(
        f"/api/v1/projects/{project_id}/timing",
        json=shifted_timing_payload(initial_timing["timingVersion"]),
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "TIMING_VERSION_CONFLICT"

    reset = client.post(
        f"/api/v1/projects/{project_id}/timing/reset",
        json={
            "expectedVersion": result["timingVersion"],
            "requantize": "all",
            "preserveManualEdits": True,
        },
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["source"] == "AI"
    assert reset.json()["barOneSeconds"] == initial_timing["barOneSeconds"]


def test_timing_validation_requires_bar_one_to_match_first_downbeat(
    client: TestClient, app
) -> None:
    project = ready_project(client, app)
    timing = client.get(f"/api/v1/projects/{project['id']}/timing").json()
    payload = shifted_timing_payload(timing["timingVersion"])
    payload["barOneSeconds"] = 0.4
    response = client.patch(f"/api/v1/projects/{project['id']}/timing", json=payload)
    assert response.status_code == 422
