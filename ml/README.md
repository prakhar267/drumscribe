# DrumScribe ML workspace

This optional workspace holds dataset governance and evaluation tooling. It never
downloads data during installation.

Dataset manifests record source version, checksums, license/attribution, performer
grouping, and paths. Deterministic splitting groups by `groupId`, preventing takes
from the same song/performer leaking across train, validation, and test.

```bash
uv sync --project ml --extra dev
uv run --project ml drumscribe-ml manifest validate dataset.json
uv run --project ml drumscribe-ml manifest split dataset.json split.json --seed drumscribe-v1
uv run --project ml drumscribe-benchmark examples/benchmark-input.json --json report.json --html report.html
```

Benchmark input schema:

```json
{
  "songs": [{
    "id": "track-1",
    "condition": "clean_stem",
    "durationSeconds": 30.0,
    "references": [{"instrument": "KICK", "onsetSeconds": 0.5}],
    "predictions": [{"instrument": "KICK", "onsetSeconds": 0.52}]
  }]
}
```

The default onset tolerance is 50 ms. Reports contain per-canonical-class and
coarse-family metrics, macro/micro/per-song F1, event-count error, FP/FN per
minute, and matched-hit timing MAE.
