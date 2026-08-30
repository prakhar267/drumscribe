import pytest

from drumscribe_ml.bakeoff import evaluate_candidates


def test_bakeoff_ranks_candidates_on_the_same_reference_set():
    reference = {
        "evidenceLevel": "rights_cleared_test",
        "songs": [
            {
                "id": "song",
                "durationSeconds": 4,
                "condition": "full_mix",
                "references": [
                    {"instrument": "KICK", "onsetSeconds": 1},
                    {"instrument": "SNARE", "onsetSeconds": 2},
                ],
            }
        ],
    }
    result = evaluate_candidates(
        reference,
        {
            "yourmt3_plus": {
                "songs": [
                    {
                        "id": "song",
                        "predictions": [
                            {"instrument": "KICK", "onsetSeconds": 1.01},
                            {"instrument": "SNARE", "onsetSeconds": 2.01},
                        ],
                    }
                ]
            },
            "spectral": {
                "songs": [
                    {
                        "id": "song",
                        "predictions": [{"instrument": "KICK", "onsetSeconds": 1.01}],
                    }
                ]
            },
        },
    )
    assert [item["candidate"] for item in result["ranking"]] == [
        "yourmt3_plus",
        "spectral",
    ]
    assert result["ranking"][0]["f1At50ms"] == 1
    assert result["reports"]["yourmt3_plus"]["evidenceLevel"] == "rights_cleared_test"


def test_bakeoff_rejects_incomplete_candidate_song_sets():
    reference = {"songs": [{"id": "song", "durationSeconds": 1, "references": []}]}
    with pytest.raises(ValueError, match="exactly match"):
        evaluate_candidates(reference, {"missing": {"songs": []}})
