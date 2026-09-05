import json
from pathlib import Path
from runpy import run_path


def _module():
    repository = Path(__file__).resolve().parents[2]
    return run_path(
        repository / "scripts" / "run_novel_cross_genre_live_benchmark.py"
    )


def test_extended_styles_are_assigned_to_declared_genre_groups():
    category = _module()["benchmark_category"]

    assert category("rock-prog") == "heavy_rock_punk"
    assert category("dance-breakbeat") == "funk_hiphop"
    assert category("dance-disco") == "pop_soul"
    assert category("middleeastern") == "jazz_world"


def test_star_reference_uses_the_official_five_class_reduction(tmp_path):
    annotation = tmp_path / "reference.txt"
    annotation.write_text(
        "0.10 BD 100\n"
        "0.20 SD 100\n"
        "0.30 OHH 100\n"
        "0.40 MT 100\n"
        "0.50 RD 100\n"
        "0.60 CL 100\n"
        "1.10 BD 100\n",
        encoding="utf-8",
    )
    reference_events = _module()["item_reference_events"]

    assert reference_events(
        {
            "dataset": "star_drums_preview",
            "annotationPath": str(annotation),
            "scoredSeconds": 1.0,
        }
    ) == [
        (0.1, "KICK"),
        (0.2, "SNARE"),
        (0.3, "HIHAT"),
        (0.4, "TOM"),
        (0.5, "CYMBAL"),
    ]


def test_groove_selection_is_balanced_deterministic_and_hash_excluding(tmp_path):
    records = []
    styles = {
        "heavy_rock_punk": "rock",
        "pop_soul": "pop",
        "funk_hiphop": "funk",
        "jazz_world": "jazz",
    }
    for group, style in styles.items():
        for index in range(6):
            records.append(
                {
                    "trackId": f"{group}/{index}",
                    "audioPath": f"{index}_{style}_120_beat_4-4.wav",
                    "annotationPath": f"{group}-{index}.json",
                    "audioSha256": f"{group}-{index}",
                    "durationSeconds": 21.0,
                    "split": "train",
                }
            )
    prepared = tmp_path / "prepared.json"
    prepared.write_text(json.dumps({"records": records}), encoding="utf-8")
    select = _module()["choose_groove_records"]

    first = select(prepared, {"heavy_rock_punk-0"})
    second = select(prepared, {"heavy_rock_punk-0"})

    assert [record["trackId"] for record in first] == [
        record["trackId"] for record in second
    ]
    assert len(first) == 20
    assert {record["category"] for record in first} == set(styles)
    assert all(
        sum(record["category"] == group for record in first) == 5
        for group in styles
    )
    assert all(record["audioSha256"] != "heavy_rock_punk-0" for record in first)


def test_frozen_manifest_item_hashes_are_enforced(tmp_path):
    audio = tmp_path / "audio.wav"
    annotation = tmp_path / "annotation.json"
    audio.write_bytes(b"audio")
    annotation.write_text("{}", encoding="utf-8")
    module = _module()
    sha256 = module["sha256"]
    verify = module["verify_manifest_items"]
    item = {
        "audioPath": str(audio),
        "audioSha256": sha256(audio),
        "annotationPath": str(annotation),
        "annotationSha256": sha256(annotation),
    }

    verify([item])
    audio.write_bytes(b"changed")

    try:
        verify([item])
    except RuntimeError as error:
        assert "benchmark audio changed" in str(error)
    else:
        raise AssertionError("changed benchmark audio was accepted")
