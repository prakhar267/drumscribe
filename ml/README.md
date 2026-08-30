# DrumScribe ML workspace

This workspace holds the commercially gated self-hosted model lifecycle and
evaluation tooling. It never downloads datasets or pretrained weights.

Dataset manifests record source version, checksums, license/attribution, performer
grouping, and paths. Deterministic splitting groups by `groupId`, preventing takes
from the same song/performer leaking across train, validation, and test.

```bash
uv sync --project ml --extra dev
uv run --project ml drumscribe-ml manifest validate dataset.json
uv run --project ml drumscribe-ml manifest split dataset.json split.json --seed drumscribe-v1
uv run --project ml drumscribe-ml prepare dataset.json /licensed/data ./prepared --seed release-v1
uv sync --project ml --extra train
uv run --project ml drumscribe-ml train training-config.json
uv run --project ml drumscribe-benchmark benchmark-input.json --json report.json --html report.html
uv run --project ml drumscribe-separation-benchmark separation-input.json --json separation.json --html separation.html
```

Licensed Groove ingestion and the strict accuracy release gate are reproducible:

```bash
uv sync --project ml --extra data --extra train --group dev
uv run --project ml drumscribe-ml import-groove \
  data/licensed-corpus/groove \
  data/licensed-corpus/groove-manifest.json \
  --archive data/licensed-corpus/groove-v1.0.0.zip
uv run --project ml drumscribe-ml prepare \
  data/licensed-corpus/groove-manifest.json \
  data/licensed-corpus/groove \
  data/licensed-corpus/groove-prepared \
  --seed groove-v1-release --augmentation-variants 0
uv run --project ml drumscribe-ml train ml/configs/groove-v1.json
uv run --project ml drumscribe-ml quality-gate benchmark.json release-evidence.json
```

The importer checks Google's published archive digest, records per-file digests,
preserves the official split, reports and excludes corrupt audio/annotation pairs,
and supports both 16-bit and 24-bit PCM. Validation and test recordings are never
augmented. The 99% gate is defined in `docs/ACCURACY_99_RELEASE_GATE.md`; missing
evidence fails.

Preparation verifies commercial-use and derivative-work flags, checks audio
hashes/durations, preserves original labels while canonicalizing annotations,
keeps performance families in one split, creates deterministic bounded
augmentations, and caches log-mel features. Training is configuration-driven and
implements a convolutional + bidirectional GRU multi-label onset network with a
velocity head, checkpoint/resume, early stopping, metric logs, experiment IDs,
Git/dataset/config provenance, and model hashes. PyTorch is an explicit optional
extra; no checkpoint is production-approved merely because this code can train it.

Validation confidence can be calibrated from an NPZ containing `logits` and
binary `targets`:

```bash
uv run --project ml drumscribe-ml calibrate validation.npz calibration.json
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

Reports include 25/50/100 ms onset tolerances, per-canonical-class and
coarse-family metrics, macro/micro/per-song F1, event-count error, FP/FN per
minute, timing MAE, correction burden, and provider-combination quality,
latency, and cost. The committed reports are explicitly synthetic tooling checks,
not evidence of production quality. A real benchmark remains blocked until a
rights-cleared corpus and commercial provider credentials are supplied.
