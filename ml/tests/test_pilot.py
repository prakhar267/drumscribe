import json

import pytest

from drumscribe_ml.pilot import PilotDatasetError, create_pilot_dataset


def _prepared_payload():
    return {
        "schemaVersion": 1,
        "dataset": {"name": "fixture", "version": "1"},
        "datasetManifestHash": "abc",
        "records": [
            {
                "trackId": f"{split}-{group}-{variant}",
                "groupId": f"{split}-{group}",
                "split": split,
                "variant": variant,
            }
            for split, groups in (("train", range(4)), ("validation", range(3)), ("test", range(2)))
            for group in groups
            for variant in ("original", "augmented")
        ],
    }


def test_pilot_selection_is_deterministic_grouped_and_excludes_test(tmp_path):
    source = tmp_path / "prepared.json"
    source.write_text(json.dumps(_prepared_payload()), encoding="utf-8")
    first = create_pilot_dataset(
        source, tmp_path / "first.json", seed="pilot-1", train_groups=2, validation_groups=1
    )
    second = create_pilot_dataset(
        source, tmp_path / "second.json", seed="pilot-1", train_groups=2, validation_groups=1
    )
    first_payload = json.loads(first.read_text())
    second_payload = json.loads(second.read_text())
    assert first_payload == second_payload
    assert {row["split"] for row in first_payload["records"]} == {"train", "validation"}
    assert len(first_payload["records"]) == 6
    selected = first_payload["pilotSelection"]["selectedGroups"]
    assert len(selected["train"]) == 2
    assert len(selected["validation"]) == 1
    assert first_payload["sourcePreparedDatasetSha256"]


def test_pilot_rejects_cross_split_groups_and_oversized_requests(tmp_path):
    payload = _prepared_payload()
    payload["records"][0]["groupId"] = payload["records"][-1]["groupId"]
    source = tmp_path / "crossed.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PilotDatasetError, match="crosses"):
        create_pilot_dataset(
            source, tmp_path / "crossed-pilot.json", seed="x", train_groups=1, validation_groups=1
        )

    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps(_prepared_payload()), encoding="utf-8")
    with pytest.raises(PilotDatasetError, match="only 4"):
        create_pilot_dataset(
            valid, tmp_path / "large.json", seed="x", train_groups=5, validation_groups=1
        )
