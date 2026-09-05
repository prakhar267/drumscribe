import json
from pathlib import Path
from runpy import run_path

import pytest


def _module():
    repository = Path(__file__).resolve().parents[2]
    return run_path(repository / "scripts" / "run_real_song_100_live_benchmark.py")


def test_family5_maps_articulations_deduplicates_unisons_and_bounds_window():
    family5 = _module()["_family5"]

    assert family5(
        [
            (0.5, "KICK"),
            (0.5, "KICK"),
            (1.0, "SNARE"),
            (1.0, "CROSS_STICK"),
            (2.0, "OPEN_HIHAT"),
            (3.0, "HIGH_TOM"),
            (4.0, "RIDE_BELL"),
            (5.0, "TAMBOURINE"),
            (20.0, "CRASH"),
        ]
    ) == [
        (0.5, "KICK"),
        (1.0, "SNARE"),
        (2.0, "HIHAT"),
        (3.0, "TOM"),
        (4.0, "CYMBAL"),
    ]


def test_selection_validation_rejects_changed_audio_hash(tmp_path):
    validate = _module()["validate_selection_manifest"]
    records = [
        {"sequence": sequence, "recordId": f"record-{sequence}", "audioSha256": "a"}
        for sequence in range(1, 101)
    ]
    manifest = {
        "recordCount": 100,
        "records": [
            {
                "sequence": record["sequence"],
                "recordId": record["recordId"],
                "audioSha256": record["audioSha256"],
            }
            for record in records
        ],
    }
    destination = tmp_path / "selection.json"
    destination.write_text(json.dumps(manifest), encoding="utf-8")

    validate(records, destination)
    records[-1]["audioSha256"] = "changed"
    with pytest.raises(RuntimeError, match="selection manifest changed"):
        validate(records, destination)


def test_group_scores_keeps_small_genres_visible():
    group_scores = _module()["_group_scores"]
    records = [{"genre": "pop"}, {"genre": "pop"}, {"genre": "jazz"}]
    references = [[(0.1, "KICK")], [(0.2, "SNARE")], [(0.3, "HIHAT")]]
    drumscribe = [[(0.1, "KICK")], [], [(0.3, "HIHAT")]]
    drum2notes = [[], [(0.2, "SNARE")], []]

    result = group_scores(records, references, drumscribe, drum2notes, "genre")

    assert result["jazz"]["recordCount"] == 1
    assert result["jazz"]["drumscribe"]["50ms"]["micro"]["f1"] == 1.0
    assert result["pop"]["drum2notes"]["50ms"]["micro"]["f1"] == pytest.approx(2 / 3)
