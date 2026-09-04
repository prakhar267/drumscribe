from pathlib import Path
from runpy import run_path


def _module():
    repository = Path(__file__).resolve().parents[2]
    return run_path(repository / "scripts" / "run_rwc_popular_50_benchmark.py")


def test_selection_is_deterministic_and_excludes_drumless_tracks():
    select_popular_tracks = _module()["select_popular_tracks"]
    rows = [
        {
            "RWCID": f"RWC_P{index:03d}",
            "CollID": "P",
            "DrumInformation": "Without drums" if index in {2, 9} else "Live drums",
        }
        for index in range(1, 12)
    ]
    rows.append({"RWCID": "RWC_J001", "CollID": "J", "DrumInformation": "Live drums"})

    first = select_popular_tracks(rows, count=5, seed="test-seed")
    second = select_popular_tracks(list(reversed(rows)), count=5, seed="test-seed")

    assert [row["RWCID"] for row in first] == [row["RWCID"] for row in second]
    assert len(first) == 5
    assert all(row["CollID"] == "P" for row in first)
    assert all(row["DrumInformation"] != "Without drums" for row in first)


def test_active_window_is_bounded_and_reference_times_are_clip_relative():
    module = _module()
    active_window = module["active_window"]
    window_events = module["window_events"]
    events = [(0.2, "KICK"), (0.9, "SNARE"), (1.3, "KICK"), (2.2, "CRASH")]

    assert active_window(events, audio_start=0.5, audio_end=5.0, duration=2.0) == 0.5
    assert window_events(events, start=0.5, duration=1.0) == [
        (0.4, "SNARE"),
        (0.8, "KICK"),
    ]

    late_events = [(9.5, "KICK")]
    assert active_window(late_events, audio_start=0.0, audio_end=10.0, duration=2.0) == 8.0


def test_drum_type_normalizes_metadata_categories():
    drum_type = _module()["drum_type"]

    assert drum_type("Live drums") == "live"
    assert drum_type("Drum sequences") == "sequences"
    assert drum_type("Drum loops") == "loops"
