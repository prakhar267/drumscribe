#!/usr/bin/env python3
"""Run isolated anonymous-user journeys concurrently against the public API.

This is an opt-in production probe. It uses one new anonymous account per user,
uploads the same rights-cleared audio, waits for every job to become terminal,
checks that READY projects expose events and timing, and deletes every test
account before exiting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

TERMINAL_STAGES = {"READY", "FAILED", "CANCELLED"}


def audio_content_type(filename: str) -> str:
    suffix = Path(filename).suffix.casefold()
    return {
        ".flac": "audio/flac",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
    }.get(suffix, "application/octet-stream")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def checked(response: httpx.Response, expected: set[int]) -> dict[str, Any]:
    if response.status_code not in expected:
        raise RuntimeError(
            f"{response.request.method} {response.request.url} returned "
            f"{response.status_code}: {response.text[:500]}"
        )
    if not response.content:
        return {}
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError(f"Expected an object from {response.request.url}")
    return payload


@dataclass
class Journey:
    index: int
    client: httpx.Client
    user_id: str
    project_id: str
    preparation_seconds: float
    job_id: str | None = None
    submitted_at: str | None = None
    submission_offset_seconds: float | None = None
    transitions: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)


def prepare_journey(
    index: int,
    *,
    base_url: str,
    audio: bytes,
    filename: str,
    session_token: str | None = None,
) -> Journey:
    started = time.monotonic()
    authenticated = False
    client = httpx.Client(
        base_url=base_url,
        follow_redirects=True,
        timeout=httpx.Timeout(90.0, connect=15.0),
        headers={"User-Agent": "DrumToScore-production-concurrency-probe/1"},
    )
    try:
        if session_token:
            client.headers["Authorization"] = f"Bearer {session_token}"
            account = checked(client.get("/api/v1/account/me"), {200})
            user_id = str(account["id"])
            authenticated = True
        else:
            session = checked(client.post("/api/v1/auth/anonymous-session"), {200, 201})
            user_id = str(session["user"]["id"])
            authenticated = True
        project = checked(
            client.post(
                "/api/v1/projects",
                json={"title": f"Production concurrency probe {index}"},
            ),
            {201},
        )
        project_id = str(project["id"])
        presign = checked(
            client.post(
                f"/api/v1/projects/{project_id}/uploads/presign",
                json={
                    "filename": filename,
                    "contentType": audio_content_type(filename),
                    "sizeBytes": len(audio),
                    "rightToUploadConfirmed": True,
                },
            ),
            {201},
        )
        # Use a separate client for the presigned storage request. Reusing the
        # API client would forward its Authorization header in registered mode,
        # leaking the app session token and invalidating the S3 signature.
        upload = httpx.put(
            str(presign["uploadUrl"]),
            content=audio,
            headers=dict(presign["requiredHeaders"]),
            timeout=httpx.Timeout(180.0, connect=15.0),
        )
        if upload.status_code not in {200, 201, 204}:
            redacted_url = upload.request.url.copy_with(query=None)
            raise RuntimeError(
                f"PUT {redacted_url} returned {upload.status_code}: {upload.text[:500]}"
            )
        checked(client.post(f"/api/v1/uploads/{presign['assetId']}/complete", json={}), {200})
        return Journey(
            index=index,
            client=client,
            user_id=user_id,
            project_id=project_id,
            preparation_seconds=round(time.monotonic() - started, 3),
        )
    except Exception:
        if authenticated:
            try:
                client.request(
                    "DELETE",
                    "/api/v1/account",
                    json={"confirmation": "DELETE MY ACCOUNT"},
                    timeout=90,
                )
            except httpx.HTTPError as cleanup_error:
                print(f"preparation_cleanup_failed={type(cleanup_error).__name__}", flush=True)
        client.close()
        raise


def submit_journey(journey: Journey, barrier: threading.Barrier, epoch: float) -> None:
    barrier.wait(timeout=30)
    journey.submission_offset_seconds = round(time.monotonic() - epoch, 4)
    response = checked(
        journey.client.post(
            f"/api/v1/projects/{journey.project_id}/process",
            json={},
            headers={"Idempotency-Key": f"production-load-{journey.project_id}"},
        ),
        {202},
    )
    journey.job_id = str(response["id"])
    journey.submitted_at = utc_now()


def observe(journeys: list[Journey], *, timeout_seconds: float, poll_seconds: float) -> None:
    started = time.monotonic()
    pending = {journey.index for journey in journeys}
    last_stage: dict[int, str] = {}
    while pending:
        elapsed = time.monotonic() - started
        if elapsed > timeout_seconds:
            raise TimeoutError(f"Timed out with journeys still pending: {sorted(pending)}")
        for journey in journeys:
            if journey.index not in pending:
                continue
            assert journey.job_id is not None
            status = checked(journey.client.get(f"/api/v1/jobs/{journey.job_id}"), {200})
            stage = str(status["stage"])
            if last_stage.get(journey.index) != stage:
                transition = {
                    "stage": stage,
                    "elapsedSeconds": round(elapsed, 3),
                    "observedAt": utc_now(),
                }
                journey.transitions.append(transition)
                last_stage[journey.index] = stage
                print(json.dumps({"journey": journey.index, **transition}), flush=True)
            if stage in TERMINAL_STAGES:
                journey.result = {
                    "stage": stage,
                    "elapsedSeconds": round(elapsed, 3),
                    "retryCount": int(status.get("retryCount", 0)),
                    "errorCode": status.get("errorCode"),
                    "errorMessage": status.get("errorMessage"),
                }
                if stage == "READY":
                    events = checked(
                        journey.client.get(f"/api/v1/projects/{journey.project_id}/events"),
                        {200},
                    )
                    timing = checked(
                        journey.client.get(f"/api/v1/projects/{journey.project_id}/timing"),
                        {200},
                    )
                    journey.result.update(
                        {
                            "eventCount": len(events.get("items", [])),
                            "beatCount": len(timing.get("beats", [])),
                            "tempoBpm": timing.get("segments", [{}])[0].get("bpm")
                            if timing.get("segments")
                            else None,
                        }
                    )
                pending.remove(journey.index)
        if pending:
            time.sleep(poll_seconds)


def cleanup(journeys: list[Journey]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for journey in journeys:
        try:
            response = journey.client.request(
                "DELETE",
                "/api/v1/account",
                json={"confirmation": "DELETE MY ACCOUNT"},
                timeout=90,
            )
            results.append(
                {
                    "journey": journey.index,
                    "statusCode": response.status_code,
                    "deleted": response.status_code == 200,
                }
            )
        finally:
            journey.client.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--base-url", default="https://drumtoscore.com")
    parser.add_argument("--users", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if not 1 <= args.users <= 20:
        parser.error("--users must be between 1 and 20")
    audio = args.audio.read_bytes()
    session_token = os.environ.get("DRUMTOSCORE_PROBE_SESSION_TOKEN")
    if session_token and args.users != 1:
        parser.error("DRUMTOSCORE_PROBE_SESSION_TOKEN can only be used with --users 1")
    run_started_at = utc_now()
    run_started = time.monotonic()
    journeys: list[Journey] = []
    cleanup_results: list[dict[str, Any]] = []
    try:
        with ThreadPoolExecutor(max_workers=args.users) as executor:
            futures = [
                executor.submit(
                    prepare_journey,
                    index,
                    base_url=args.base_url.rstrip("/"),
                    audio=audio,
                    filename=args.audio.name,
                    session_token=session_token,
                )
                for index in range(1, args.users + 1)
            ]
            for future in as_completed(futures):
                journeys.append(future.result())
        journeys.sort(key=lambda item: item.index)
        submit_epoch = time.monotonic()
        barrier = threading.Barrier(args.users)
        with ThreadPoolExecutor(max_workers=args.users) as executor:
            futures = [
                executor.submit(submit_journey, journey, barrier, submit_epoch)
                for journey in journeys
            ]
            for future in futures:
                future.result()
        observe(
            journeys,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
    finally:
        cleanup_results = cleanup(journeys)
    report = {
        "schemaVersion": 1,
        "startedAt": run_started_at,
        "baseUrl": args.base_url.rstrip("/"),
        "users": args.users,
        "authentication": "registered" if session_token else "anonymous",
        "audio": {
            "filename": args.audio.name,
            "sizeBytes": len(audio),
            "sha256": hashlib.sha256(audio).hexdigest(),
        },
        "wallSeconds": round(time.monotonic() - run_started, 3),
        "journeys": [
            {
                "index": journey.index,
                "userId": journey.user_id,
                "projectId": journey.project_id,
                "jobId": journey.job_id,
                "preparationSeconds": journey.preparation_seconds,
                "submissionOffsetSeconds": journey.submission_offset_seconds,
                "transitions": journey.transitions,
                "result": journey.result,
            }
            for journey in journeys
        ],
        "cleanup": cleanup_results,
    }
    print("FINAL_REPORT=" + json.dumps(report, sort_keys=True), flush=True)
    return 0 if all(item.result.get("stage") == "READY" for item in journeys) else 1


if __name__ == "__main__":
    raise SystemExit(main())
