"""Reproducible onset benchmark with JSON and self-contained HTML reports."""

from __future__ import annotations

import argparse
import html
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from drumscribe_music import Instrument, canonical_instrument


@dataclass(frozen=True, slots=True)
class EvaluationHit:
    instrument: Instrument
    onset_seconds: float

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EvaluationHit:
        onset = float(value["onsetSeconds"])
        if not math.isfinite(onset) or onset < 0:
            raise ValueError("benchmark onsets must be finite and non-negative")
        return cls(canonical_instrument(value["instrument"]), onset)


FAMILIES: dict[str, frozenset[Instrument]] = {
    "KICK": frozenset({Instrument.KICK}),
    "SNARE": frozenset({Instrument.SNARE, Instrument.CROSS_STICK}),
    "HI_HAT": frozenset({Instrument.CLOSED_HIHAT, Instrument.OPEN_HIHAT, Instrument.PEDAL_HIHAT}),
    "TOMS": frozenset(
        {
            Instrument.HIGH_TOM,
            Instrument.MID_TOM,
            Instrument.LOW_TOM,
            Instrument.FLOOR_TOM,
        }
    ),
    "CYMBALS": frozenset({Instrument.RIDE, Instrument.RIDE_BELL, Instrument.CRASH}),
}


def evaluate_payload(payload: dict[str, Any], *, tolerance_seconds: float = 0.05) -> dict[str, Any]:
    if not 0 < tolerance_seconds <= 1:
        raise ValueError("tolerance_seconds must be greater than 0 and at most 1")
    songs = payload.get("songs")
    if not isinstance(songs, list) or not songs:
        raise ValueError("benchmark payload must contain a non-empty songs array")
    totals = {instrument: _empty_counts() for instrument in Instrument}
    class_errors: dict[Instrument, list[float]] = {instrument: [] for instrument in Instrument}
    family_totals = {name: _empty_counts() for name in FAMILIES}
    song_reports = []
    condition_totals: dict[str, dict[str, int]] = {}
    condition_durations: dict[str, float] = {}
    condition_errors: dict[str, list[float]] = {}
    total_duration = 0.0
    all_errors: list[float] = []
    seen_ids: set[str] = set()
    for song in songs:
        song_id = str(song["id"])
        if not song_id or song_id in seen_ids:
            raise ValueError("benchmark song ids must be non-empty and unique")
        seen_ids.add(song_id)
        duration = float(song["durationSeconds"])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"song {song_id!r} duration must be positive and finite")
        references = [EvaluationHit.from_dict(value) for value in song.get("references", [])]
        predictions = [EvaluationHit.from_dict(value) for value in song.get("predictions", [])]
        condition = str(song.get("condition", "unspecified"))
        if condition not in {"clean_stem", "full_mix", "unspecified"}:
            raise ValueError(
                f"song {song_id!r} condition must be clean_stem, full_mix, or unspecified"
            )
        if any(
            hit.onset_seconds > duration + tolerance_seconds for hit in references + predictions
        ):
            raise ValueError(f"song {song_id!r} contains an onset beyond its duration")
        song_counts = _empty_counts()
        song_errors: list[float] = []
        for instrument in Instrument:
            reference_times = [
                hit.onset_seconds for hit in references if hit.instrument is instrument
            ]
            prediction_times = [
                hit.onset_seconds for hit in predictions if hit.instrument is instrument
            ]
            counts, errors = _match_onsets(reference_times, prediction_times, tolerance_seconds)
            _add_counts(totals[instrument], counts)
            _add_counts(song_counts, counts)
            class_errors[instrument].extend(errors)
            song_errors.extend(errors)
        for name, members in FAMILIES.items():
            reference_times = [hit.onset_seconds for hit in references if hit.instrument in members]
            prediction_times = [
                hit.onset_seconds for hit in predictions if hit.instrument in members
            ]
            counts, _ = _match_onsets(reference_times, prediction_times, tolerance_seconds)
            _add_counts(family_totals[name], counts)
        total_duration += duration
        all_errors.extend(song_errors)
        condition_totals.setdefault(condition, _empty_counts())
        condition_durations[condition] = condition_durations.get(condition, 0.0) + duration
        condition_errors.setdefault(condition, []).extend(song_errors)
        _add_counts(condition_totals[condition], song_counts)
        song_reports.append(
            {
                "id": song_id,
                "condition": condition,
                "durationSeconds": duration,
                **_metrics(song_counts, duration, song_errors),
                "referenceEvents": len(references),
                "predictedEvents": len(predictions),
                "eventCountError": len(predictions) - len(references),
            }
        )
    class_reports = {
        instrument.value: _metrics(counts, total_duration, class_errors[instrument])
        for instrument, counts in totals.items()
    }
    family_reports = {
        name: _metrics(counts, total_duration, []) for name, counts in family_totals.items()
    }
    active_f1 = [
        report["f1"] for report in class_reports.values() if report["support"] + report["fp"] > 0
    ]
    overall_counts = _empty_counts()
    for counts in totals.values():
        _add_counts(overall_counts, counts)
    overall = _metrics(overall_counts, total_duration, all_errors)
    reference_events = overall_counts["tp"] + overall_counts["fn"]
    predicted_events = overall_counts["tp"] + overall_counts["fp"]
    return {
        "schemaVersion": 1,
        "toleranceSeconds": tolerance_seconds,
        "songCount": len(song_reports),
        "durationSeconds": total_duration,
        "overall": {
            **overall,
            "macroF1": sum(active_f1) / len(active_f1) if active_f1 else 0.0,
            "meanPerSongF1": sum(song["f1"] for song in song_reports) / len(song_reports),
            "referenceEvents": reference_events,
            "predictedEvents": predicted_events,
            "eventCountError": predicted_events - reference_events,
            "absoluteEventCountError": abs(predicted_events - reference_events),
        },
        "classes": class_reports,
        "families": family_reports,
        "conditions": {
            name: _metrics(counts, condition_durations[name], condition_errors[name])
            for name, counts in sorted(condition_totals.items())
        },
        "songs": song_reports,
    }


def _match_onsets(
    references: Sequence[float], predictions: Sequence[float], tolerance: float
) -> tuple[dict[str, int], list[float]]:
    refs, preds = sorted(references), sorted(predictions)
    # Dynamic programming maximizes matches first and minimizes timing error second.
    rows, columns = len(refs) + 1, len(preds) + 1
    table: list[list[tuple[int, float]]] = [[(0, 0.0)] * columns for _ in range(rows)]
    decisions: list[list[str]] = [[""] * columns for _ in range(rows)]
    for row in range(1, rows):
        decisions[row][0] = "r"
    for column in range(1, columns):
        decisions[0][column] = "p"
    for row in range(1, rows):
        for column in range(1, columns):
            candidates = [(table[row - 1][column], "r"), (table[row][column - 1], "p")]
            error = abs(refs[row - 1] - preds[column - 1])
            if error <= tolerance:
                previous = table[row - 1][column - 1]
                candidates.append(((previous[0] + 1, previous[1] - error), "m"))
            score, decision = max(
                candidates, key=lambda item: (item[0][0], item[0][1], item[1] == "m")
            )
            table[row][column], decisions[row][column] = score, decision
    errors: list[float] = []
    row, column = len(refs), len(preds)
    while row or column:
        decision = decisions[row][column]
        if decision == "m":
            errors.append(abs(refs[row - 1] - preds[column - 1]))
            row -= 1
            column -= 1
        elif decision == "r":
            row -= 1
        else:
            column -= 1
    true_positive = table[-1][-1][0]
    return {
        "tp": true_positive,
        "fp": len(preds) - true_positive,
        "fn": len(refs) - true_positive,
    }, errors


def _empty_counts() -> dict[str, int]:
    return {"tp": 0, "fp": 0, "fn": 0}


def _add_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key in target:
        target[key] += source[key]


def _metrics(counts: dict[str, int], duration: float, errors: Iterable[float]) -> dict[str, Any]:
    precision = counts["tp"] / (counts["tp"] + counts["fp"]) if counts["tp"] + counts["fp"] else 0.0
    recall = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    minutes = duration / 60
    timing_errors = list(errors)
    return {
        **counts,
        "support": counts["tp"] + counts["fn"],
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "falsePositivesPerMinute": counts["fp"] / minutes,
        "falseNegativesPerMinute": counts["fn"] / minutes,
        "timingMaeSeconds": sum(timing_errors) / len(timing_errors) if timing_errors else None,
    }


def render_html_report(report: dict[str, Any]) -> str:
    class_rows = "".join(_table_row(name, metrics) for name, metrics in report["classes"].items())
    family_rows = "".join(_table_row(name, metrics) for name, metrics in report["families"].items())
    condition_rows = "".join(
        _table_row(name, metrics) for name, metrics in report["conditions"].items()
    )
    song_rows = "".join(
        _table_row(f"{song['id']} ({song['condition']})", song) for song in report["songs"]
    )
    embedded = json.dumps(report, separators=(",", ":")).replace("<", "\\u003c")
    overall = report["overall"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>DrumScribe benchmark</title><style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ max-width: 1100px; margin: 2rem auto; padding: 0 1rem; }}
.summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:.75rem; }}
.metric {{ border:1px solid #8886; border-radius:8px; padding:1rem; }}
.metric strong {{ display:block; font-size:1.5rem; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ text-align:right; padding:.45rem; border-bottom:1px solid #8885; }}
th:first-child,td:first-child {{ text-align:left; }}
</style></head><body><h1>DrumScribe transcription benchmark</h1>
<p>{report["songCount"]} songs · {report["durationSeconds"]:.2f} seconds ·
onset tolerance {report["toleranceSeconds"] * 1000:g} ms</p>
<section class="summary"><div class="metric">Micro F1<strong>{overall["f1"]:.3f}</strong></div>
<div class="metric">Macro F1<strong>{overall["macroF1"]:.3f}</strong></div>
<div class="metric">Per-song F1<strong>{overall["meanPerSongF1"]:.3f}</strong></div>
<div class="metric">Timing MAE
<strong>{_format_mae(overall["timingMaeSeconds"])}</strong></div></section>
<h2>Input conditions</h2>{_table(condition_rows)}
<h2>Canonical classes</h2>{_table(class_rows)}
<h2>Coarse families</h2>{_table(family_rows)}
<h2>Songs</h2>{_table(song_rows)}
<script id="benchmark-data" type="application/json">{embedded}</script></body></html>"""


def _table(rows: str) -> str:
    return (
        "<table><thead><tr><th>Name</th><th>P</th><th>R</th><th>F1</th>"
        "<th>TP</th><th>FP</th><th>FN</th><th>MAE</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _table_row(name: str, metrics: dict[str, Any]) -> str:
    return (
        f"<tr><td>{html.escape(name)}</td><td>{metrics['precision']:.3f}</td>"
        f"<td>{metrics['recall']:.3f}</td><td>{metrics['f1']:.3f}</td>"
        f"<td>{metrics['tp']}</td><td>{metrics['fp']}</td><td>{metrics['fn']}</td>"
        f"<td>{_format_mae(metrics.get('timingMaeSeconds'))}</td></tr>"
    )


def _format_mae(value: float | None) -> str:
    return "—" if value is None else f"{value * 1000:.1f} ms"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--tolerance-ms", type=float, default=50)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--html", type=Path, required=True, dest="html_path")
    args = parser.parse_args(argv)
    if args.json_path.resolve() == args.html_path.resolve():
        parser.error("--json and --html must be different paths")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = evaluate_payload(payload, tolerance_seconds=args.tolerance_ms / 1000)
    for path in (args.json_path, args.html_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(path)
    with args.json_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    with args.html_path.open("x", encoding="utf-8") as handle:
        handle.write(render_html_report(report))
    print(
        json.dumps(
            {
                "json": str(args.json_path),
                "html": str(args.html_path),
                "f1": report["overall"]["f1"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
