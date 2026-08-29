"""Source-separation benchmark with SI-SDR and a controlled listening rubric."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

REQUIRED_CONDITIONS = (
    "clean_studio_rock",
    "pop",
    "indie",
    "acoustic_rock",
    "dense_electric_guitars",
    "bass_heavy_mix",
    "quiet_drums",
    "loud_drums",
    "reverb_heavy_drums",
    "compressed_mastering",
    "live_recording",
)

LISTENING_DIMENSIONS = (
    "bleed",
    "cymbalEnergy",
    "kickPreservation",
    "snarePreservation",
    "tomPreservation",
    "transientIntegrity",
)


def scale_invariant_sdr(reference: np.ndarray, estimate: np.ndarray) -> float:
    reference = np.asarray(reference, dtype=np.float64).reshape(-1)
    estimate = np.asarray(estimate, dtype=np.float64).reshape(-1)
    if reference.shape != estimate.shape or not len(reference):
        raise ValueError("reference and estimate must be equally sized, non-empty arrays")
    reference -= reference.mean()
    estimate -= estimate.mean()
    energy = float(reference @ reference)
    if energy <= 1e-12:
        raise ValueError("reference must contain non-silent audio")
    target = (float(estimate @ reference) / energy) * reference
    noise = estimate - target
    return 10 * math.log10((float(target @ target) + 1e-12) / (float(noise @ noise) + 1e-12))


def evaluate_separation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    tracks = payload.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise ValueError("separation benchmark requires a non-empty tracks array")
    seen: set[str] = set()
    reports = []
    for track in tracks:
        identifier = str(track["id"])
        if not identifier or identifier in seen:
            raise ValueError("separation track IDs must be non-empty and unique")
        seen.add(identifier)
        condition = str(track["condition"])
        if condition not in REQUIRED_CONDITIONS:
            raise ValueError(f"unsupported separation condition: {condition}")
        listening = track.get("listening", {})
        if set(listening) != set(LISTENING_DIMENSIONS):
            raise ValueError("listening results must include every required rubric dimension")
        if any(not 1 <= int(value) <= 5 for value in listening.values()):
            raise ValueError("listening rubric values must be integers from 1 to 5")
        reference = track.get("referenceSamples")
        estimate = track.get("estimateSamples")
        score = (
            scale_invariant_sdr(np.asarray(reference), np.asarray(estimate))
            if reference is not None and estimate is not None
            else None
        )
        reports.append(
            {
                "id": identifier,
                "condition": condition,
                "provider": track.get("provider", "unknown"),
                "modelVersion": track.get("modelVersion", "unknown"),
                "siSdrDb": score,
                "listening": listening,
                "listeningMean": sum(int(value) for value in listening.values()) / len(listening),
            }
        )
    measured = [row["siSdrDb"] for row in reports if row["siSdrDb"] is not None]
    covered = {row["condition"] for row in reports}
    return {
        "schemaVersion": 1,
        "evidenceLevel": payload.get("evidenceLevel", "unspecified"),
        "trackCount": len(reports),
        "coverage": {
            "covered": sorted(covered),
            "missing": [name for name in REQUIRED_CONDITIONS if name not in covered],
        },
        "meanSiSdrDb": sum(measured) / len(measured) if measured else None,
        "meanListeningScore": sum(row["listeningMean"] for row in reports) / len(reports),
        "tracks": reports,
    }


def render_separation_html(report: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['id'])}</td><td>{html.escape(row['condition'])}</td>"
        f"<td>{html.escape(str(row['provider']))}</td>"
        f"<td>{_format_sisdr(row['siSdrDb'])}</td>"
        f"<td>{row['listeningMean']:.2f}/5</td></tr>"
        for row in report["tracks"]
    )
    embedded = json.dumps(report, separators=(",", ":")).replace("<", "\\u003c")
    evidence = html.escape(str(report["evidenceLevel"]))
    mean_sisdr = "—" if report["meanSiSdrDb"] is None else f"{report['meanSiSdrDb']:.2f} dB"
    missing = report["coverage"]["missing"]
    missing_notice = (
        f"<p class='blocked'>Missing required conditions: {html.escape(', '.join(missing))}</p>"
        if missing
        else ""
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>DrumScribe separation benchmark</title>
<style>body{{font:15px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:.55rem;
border-bottom:1px solid #ccc}}.blocked{{padding:1rem;border:1px solid #b66;
background:#fee}}</style></head><body>
<h1>DrumScribe source-separation benchmark</h1>
<p><strong>Evidence:</strong> {evidence}</p>
<p>{report["trackCount"]} tracks · mean listening score
{report["meanListeningScore"]:.2f}/5 · mean SI-SDR {mean_sisdr}</p>
{missing_notice}
<table><thead><tr><th>Track</th><th>Condition</th><th>Provider</th>
<th>SI-SDR dB</th><th>Listening</th></tr></thead><tbody>{rows}</tbody></table>
<script id="benchmark-data" type="application/json">{embedded}</script></body></html>"""


def _format_sisdr(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--html", type=Path, required=True, dest="html_path")
    args = parser.parse_args(argv)
    report = evaluate_separation_payload(json.loads(args.input.read_text(encoding="utf-8")))
    for destination, content in (
        (args.json_path, json.dumps(report, indent=2, sort_keys=True) + "\n"),
        (args.html_path, render_separation_html(report)),
    ):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
