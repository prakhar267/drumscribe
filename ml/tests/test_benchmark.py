import json

import pytest

from drumscribe_ml.benchmark import evaluate_benchmark, evaluate_payload, main, render_html_report


def _payload():
    return {
        "songs": [
            {
                "id": "clean-stem",
                "condition": "clean_stem",
                "durationSeconds": 60,
                "references": [
                    {"instrument": "KICK", "onsetSeconds": 1.0},
                    {"instrument": "SNARE", "onsetSeconds": 2.0},
                    {"instrument": "CLOSED_HIHAT", "onsetSeconds": 3.0},
                ],
                "predictions": [
                    {"instrument": "KICK", "onsetSeconds": 1.02},
                    {"instrument": "SNARE", "onsetSeconds": 2.08},
                    {"instrument": "CLOSED_HIHAT", "onsetSeconds": 3.0},
                    {"instrument": "CRASH", "onsetSeconds": 4.0},
                ],
            },
            {
                "id": "full-mix",
                "condition": "full_mix",
                "durationSeconds": 30,
                "references": [{"instrument": "KICK", "onsetSeconds": 0.5}],
                "predictions": [],
            },
        ]
    }


def test_benchmark_metrics_by_class_song_and_rate():
    report = evaluate_payload(_payload(), tolerance_seconds=0.05)
    assert report["classes"]["KICK"]["tp"] == 1
    assert report["classes"]["KICK"]["fn"] == 1
    assert report["classes"]["SNARE"]["fp"] == 1
    assert report["classes"]["CLOSED_HIHAT"]["f1"] == 1
    assert report["overall"]["tp"] == 2
    assert report["overall"]["fp"] == 2
    assert report["overall"]["fn"] == 2
    assert report["overall"]["f1"] == pytest.approx(0.5)
    assert report["overall"]["timingMaeSeconds"] == pytest.approx(0.01)
    assert report["overall"]["eventCountError"] == 0
    assert report["songs"][0]["falsePositivesPerMinute"] == 2
    assert set(report["conditions"]) == {"clean_stem", "full_mix"}
    assert report["conditions"]["clean_stem"]["tp"] == 2


def test_matching_maximizes_count_before_timing_error():
    payload = {
        "songs": [
            {
                "id": "ambiguous",
                "durationSeconds": 1,
                "references": [
                    {"instrument": "KICK", "onsetSeconds": 0.10},
                    {"instrument": "KICK", "onsetSeconds": 0.16},
                ],
                "predictions": [
                    {"instrument": "KICK", "onsetSeconds": 0.12},
                    {"instrument": "KICK", "onsetSeconds": 0.18},
                ],
            }
        ]
    }
    assert evaluate_payload(payload, tolerance_seconds=0.05)["overall"]["tp"] == 2


def test_html_is_self_contained_and_embeds_parseable_json():
    report = evaluate_payload(_payload())
    page = render_html_report(report)
    assert "<!doctype html>" in page and "<style>" in page and "https://" not in page
    embedded = page.split('<script id="benchmark-data" type="application/json">', 1)[1].split(
        "</script>", 1
    )[0]
    assert json.loads(embedded)["schemaVersion"] == 1


def test_benchmark_cli_writes_json_and_html(tmp_path):
    input_path = tmp_path / "input.json"
    json_path = tmp_path / "report.json"
    html_path = tmp_path / "report.html"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")
    assert (
        main(
            [
                str(input_path),
                "--json",
                str(json_path),
                "--html",
                str(html_path),
            ]
        )
        == 0
    )
    report = json.loads(json_path.read_text())
    assert report["overall"]["f1"] == pytest.approx(0.5)
    assert set(report["onsetToleranceReports"]) == {"25", "50", "100"}
    assert "Input conditions" in html_path.read_text()


def test_product_benchmark_tracks_economics_and_correction_burden():
    payload = _payload()
    payload["evidenceLevel"] = "licensed_evaluation"
    payload["songs"][0].update(
        {
            "providers": {
                "separation": "separator-v1",
                "transcription": "transcriber-v2",
                "beatTracking": "beat-v1",
            },
            "processingSeconds": 40,
            "providerCost": 0.25,
            "correctionBurden": {
                "eventsAdded": 1,
                "eventsDeleted": 2,
                "eventsMoved": 3,
                "instrumentsReassigned": 1,
                "tempoCorrections": 1,
                "barLineCorrections": 0,
                "correctionSeconds": 90,
            },
        }
    )
    report = evaluate_benchmark(payload)
    assert report["correctionBurden"]["totalCorrections"] == 8
    assert report["providerCombinations"][0]["costPerAudioMinute"] == pytest.approx(0.25)
