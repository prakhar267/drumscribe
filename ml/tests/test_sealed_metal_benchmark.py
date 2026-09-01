from collections import Counter
from pathlib import Path
from runpy import run_path

from drumscribe_music import Instrument


def _module():
    repository = Path(__file__).resolve().parents[2]
    return run_path(repository / "scripts" / "run_sealed_metal_benchmark.py")


def test_sealed_metal_reference_is_deterministic_and_supports_every_class():
    metal_events = _module()["metal_events"]
    _, first = metal_events()
    _, second = metal_events()
    counts = Counter(event.instrument for event in first)

    assert [event.as_dict() for event in first] == [event.as_dict() for event in second]
    assert set(counts) == set(Instrument)
    assert min(counts.values()) >= 8
    assert len(first) == 655
