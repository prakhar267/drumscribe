import json
from pathlib import Path
from runpy import run_path


def _module():
    repository = Path(__file__).resolve().parents[2]
    return run_path(repository / "scripts" / "run_recall_fusion_live_benchmark.py")


def test_test_split_selection_is_balanced_deterministic_and_style_diverse(tmp_path):
    records = []
    styles = {
        "heavy_rock_punk": ("rock", "rock-prog"),
        "pop_soul": ("pop", "soul"),
        "funk_hiphop": ("funk", "hiphop"),
        "jazz_world": ("jazz", "latin"),
    }
    for group, group_styles in styles.items():
        for index in range(6):
            style = group_styles[index % len(group_styles)]
            records.append(
                {
                    "trackId": f"{group}/{index}",
                    "audioPath": f"{index}_{style}_120_beat_4-4.wav",
                    "annotationPath": f"{group}-{index}.json",
                    "audioSha256": f"{group}-{index}",
                    "durationSeconds": 21.0,
                    "split": "test",
                }
            )
    records.append(
        {
            "trackId": "ignored-train",
            "audioPath": "0_rock_120_beat_4-4.wav",
            "annotationPath": "ignored.json",
            "audioSha256": "ignored",
            "durationSeconds": 21.0,
            "split": "train",
        }
    )
    prepared = tmp_path / "prepared.json"
    prepared.write_text(json.dumps({"records": records}), encoding="utf-8")
    select = _module()["choose_records"]

    first = select(prepared)
    second = select(prepared)

    assert [record["trackId"] for record in first] == [
        record["trackId"] for record in second
    ]
    assert len(first) == 20
    assert all(record["split"] == "test" for record in first)
    assert all(
        sum(record["category"] == group for record in first) == 5
        for group in styles
    )


def test_report_identifies_internal_locked_verification(monkeypatch, tmp_path):
    report = {
        "benchmark": {},
        "categories": {"star_full_mix": {}, "pop_soul": {}},
        "systems": {"drumscribe": {}},
    }
    module = _module()
    monkeypatch.setitem(
        module["revise_report"].__globals__,
        "detailed_articulation_scores",
        lambda items, output_root: {"drumscribe": {}, "drum2notes": {}},
    )
    prediction_root = tmp_path / "drumscribe-raw"
    prediction_root.mkdir()
    (prediction_root / "001.json").write_text(
        '{"modelVersion":"drumscribe-recall-fusion-v1"}', encoding="utf-8"
    )

    revised = module["revise_report"](report, [], tmp_path)

    assert revised["benchmark"]["selectionFrozenBeforeInference"] is True
    assert revised["benchmark"]["sourceSplit"] == "test"
    assert "star_full_mix" not in revised["categories"]
