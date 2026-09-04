# RWC Popular temporal stacker improvement v20

Date completed: 2026-09-04

## Result

DrumScribe v20 improves the same 89-song RWC Popular research benchmark from
**60.48% to 61.53% detailed 14-class micro F1 at ±50 ms**, a **+1.05 percentage
point** absolute gain over v19. At the stricter ±20 ms tolerance, detailed F1
improves from **38.70% to 46.45%**, a larger **+7.76 point** gain.

The exact public benchmark scorer—not a rounded frame approximation—produces all
release numbers below. V20 is still far below 90% and is not production or
commercially approved.

## Like-for-like results

| Partition | Evaluation protocol | Songs | v19 ±50 ms | v20 ±50 ms | Gain |
| --- | --- | ---: | ---: | ---: | ---: |
| First 50 | Track-wise five-fold out-of-fold stacker prediction | 50 | 58.85% | **60.45%** | **+1.59 pp** |
| Remainder | Previously opened secondary evaluation; no v20 retuning | 39 | 62.80% | **63.08%** | **+0.28 pp** |
| **Combined** | OOF development plus fixed secondary evaluation | **89** | **60.48%** | **61.53%** | **+1.05 pp** |

Combined taxonomy results at ±50 ms:

| Metric | v19 | v20 | Gain |
| --- | ---: | ---: | ---: |
| Detailed 14-class micro F1 | 60.48% | **61.53%** | +1.05 pp |
| Six-family micro F1 | 63.33% | **64.62%** | +1.29 pp |
| Core kick/snare/hi-hat micro F1 | 69.34% | **70.42%** | +1.09 pp |
| Class-agnostic onset F1 | 74.09% | **75.66%** | +1.57 pp |

Combined strict-timing results at ±20 ms:

| Metric | v19 | v20 | Gain |
| --- | ---: | ---: | ---: |
| Detailed 14-class micro F1 | 38.70% | **46.45%** | +7.76 pp |
| Six-family micro F1 | 40.71% | **49.08%** | +8.37 pp |
| Core kick/snare/hi-hat micro F1 | 44.59% | **53.82%** | +9.24 pp |
| Class-agnostic onset F1 | 48.60% | **58.67%** | +10.07 pp |

## What changed

V20 adds a compact temporal stacker over the same four v19 probability streams.
For each frame it sees seven neighboring positions from the stem ensemble, stem
specialist, mixture ensemble and mixture specialist. A two-layer calibrated MLP
learns cross-class and cross-view relationships while retaining simultaneous drum
hits.

The stacker is evaluated track-wise: each of the first 50 songs is predicted by a
model trained on the other four folds. Only the final research checkpoint is fitted
on all 50 development songs. The frozen event fusion uses the stacker to recover
closed-hi-hat and crash candidates; the other classes stay on the stronger v19
stream.

During validation, an integrity check exposed that the actual feature clock is
`220 / 22050 = 0.009977324...` seconds per frame, not exactly 10 ms. V20 now uses
that exact clock throughout training, decoding and evaluation and applies frozen
per-class latency offsets. This accounts for most of the strict ±20 ms gain.

## Secondary-partition behavior

On the 39-song secondary partition, v20 reaches 63.08% detailed F1, 66.23%
six-family F1, 72.29% core-three F1 and 73.48% class-agnostic onset F1 at ±50 ms.
Crash F1 improves from 30.17% to 48.70%. Closed-hi-hat fusion does not transfer as
well as it did out of fold, limiting the net ±50 ms improvement. The fixed timing
alignment raises detailed F1 at ±20 ms from 39.99% to 50.90% before stacker fusion.

This partition was opened during v19 evaluation. It is useful secondary evidence,
but it is no longer an untouched holdout and must not be marketed as one.

## Integrity and limitations

- Corpus: RWC 2.0 Popular Music Database and aligned annotations, CC BY-NC 4.0.
- Audio: the identical 89 deterministic 20-second excerpts and identical Demucs
  stems used by v19; 1,780 scored seconds and 12,454 reference events.
- Matching: one-to-one, class-aware event matching at ±20 ms and ±50 ms.
- Development protocol: five track-wise folds; decoder fitting occurs only on each
  fold's training tracks before its out-of-fold predictions are generated.
- The base timing offsets and final fusion modes/radii were selected from all 50
  out-of-fold predictions. The first-50 result is development evidence, not a
  sealed holdout score.
- Secondary protocol: the final first-50 checkpoint/config was frozen before the
  39-song v20 evaluation was run.
- V20 is trained against non-commercial RWC annotations and depends on the v19
  Demucs research path. It cannot be shipped in the paid product.
- Detailed toms, pedal hi-hat, ride, ride bell and tambourine remain effectively
  unsupported on natural mixtures. A 90% claim is not justified.

## Reproduction

```bash
# Rebuild the five-fold evidence and final research checkpoint from the saved
# first-50 probability streams.
PYTHONPATH=ml/src:scripts uv run --project ml python \
  scripts/train_rwc_temporal_stacker.py

# Cache the identical four model streams for the secondary partition.
PYTHONPATH=ml/src:scripts uv run --project ml python \
  scripts/run_rwc_multiview_benchmark.py \
  --data-root data/research-corpus/rwc-popular-holdout-39-v1 \
  --output output/rwc-popular-holdout-39-v19/benchmark-result.json \
  --probability-cache-root output/rwc-popular-holdout-39-v20/probabilities

# Apply the frozen v20 checkpoint and score it.
PYTHONPATH=ml/src:scripts uv run --project ml python \
  scripts/run_rwc_temporal_stacker_benchmark.py
```

Committed compact evidence is in
`docs/benchmarks/data/RWC_POPULAR_TEMPORAL_STACKER_V20.json`. Full probability
caches, source audio, references and raw predictions remain gitignored.
