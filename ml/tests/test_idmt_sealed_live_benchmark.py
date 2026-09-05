from pathlib import Path
from runpy import run_path


def _module():
    repository = Path(__file__).resolve().parents[2]
    return run_path(repository / "scripts" / "run_idmt_sealed_live_benchmark.py")


def test_parse_svl_uses_model_sample_rate_and_limit(tmp_path):
    annotation = tmp_path / "sample.svl"
    annotation.write_text(
        """<?xml version="1.0"?>
<sv><data><model sampleRate="100"/><dataset>
<point frame="5"/><point frame="100"/><point frame="250"/>
</dataset></data></sv>
""",
        encoding="utf-8",
    )

    events = _module()["parse_svl"](annotation, "KICK", 2.0)

    assert events == [(0.05, "KICK"), (1.0, "KICK")]


def test_discovery_is_filename_only_and_requires_all_14(tmp_path, monkeypatch):
    audio_root = tmp_path / "audio"
    annotation_root = tmp_path / "annotation_svl"
    audio_root.mkdir()
    annotation_root.mkdir()
    for index in range(14):
        track_id = f"RealDrum01_{index:02d}"
        (audio_root / f"{track_id}#MIX.wav").write_bytes(b"not opened")
        for suffix in ("KD", "SD", "HH"):
            (annotation_root / f"{track_id}#{suffix}.svl").write_text(
                "not parsed", encoding="utf-8"
            )
    module = _module()
    monkeypatch.setitem(module["discover_records"].__globals__, "EXPECTED_RECORD_COUNT", 14)

    records = module["discover_records"](tmp_path)

    assert len(records) == 14
    assert records[0]["trackId"] == "RealDrum01_00"
    assert records[-1]["trackId"] == "RealDrum01_13"


def test_opened_iteration_is_marked_as_non_independent(monkeypatch, tmp_path):
    module = _module()
    monkeypatch.setitem(
        module["score_results"].__globals__,
        "aggregate",
        lambda references, predictions: {},
    )
    (tmp_path / "selection-manifest.json").write_text("{}", encoding="utf-8")
    prediction_root = tmp_path / "drumscribe-raw"
    prediction_root.mkdir()
    (prediction_root / "001.json").write_text(
        '{"modelVersion":"drumscribe-recall-fusion-v3"}', encoding="utf-8"
    )

    report = module["score_results"](
        [],
        tmp_path,
        evaluation_status="opened_model_iteration",
        drum_only_profile="acoustic",
    )

    assert report["benchmark"]["independentModelEvaluation"] is False
    assert report["systems"]["drumscribe"]["drumOnlyProfile"] == "acoustic"
