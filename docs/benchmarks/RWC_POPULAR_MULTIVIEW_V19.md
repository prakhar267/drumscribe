# RWC Popular multi-view improvement v19

Date completed: 2026-09-04

## Result

The frozen DrumScribe v19 development candidate improved detailed 14-class
micro F1 from **50.25% to 62.80% on an untouched 39-song holdout** at ±50 ms.
That is a **+12.55 percentage-point absolute gain** over v18 on identical audio,
stems, references, and scoring. The holdout also reached **65.75% six-family
F1**, **72.23% core kick/snare/hi-hat F1**, and **72.83% class-agnostic onset
F1**.

The same frozen candidate replayed at **58.85% detailed F1** on the 50-song
development partition used to calibrate its decoder, compared with **46.48%**
for v18. Across all 89 drum-active RWC Popular tracks, v19 reaches **60.48%**
detailed F1 versus **48.05%** for v18, a **+12.43 point gain**.

This is a material improvement, but it is not 90%. It must not be described as
90% accurate, production-approved, or commercially validated.

## Like-for-like scores at ±50 ms

| Partition | Songs | Reference events | Metric | v18 | v19 | Gain |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| Opened development | 50 | 7,319 | Detailed 14-class F1 | 46.48% | 58.85% | +12.38 pp |
| **Untouched holdout** | **39** | **5,135** | **Detailed 14-class F1** | **50.25%** | **62.80%** | **+12.55 pp** |
| All RWC drum-active tracks | 89 | 12,454 | Detailed 14-class F1 | 48.05% | 60.48% | +12.43 pp |
| All RWC drum-active tracks | 89 | 12,454 | Six-family F1 | 54.28% | 63.33% | +9.05 pp |
| All RWC drum-active tracks | 89 | 10,175 core events | Core-three F1 | 59.68% | 69.34% | +9.66 pp |
| All RWC drum-active tracks | 89 | 12,454 | Class-agnostic onset F1 | — | 74.09% | — |

At the stricter ±20 ms tolerance, combined detailed F1 rises from 28.24% to
38.69%, a +10.45 point gain. The remaining difference between 74.09% onset F1
and 60.48% detailed F1 shows that instrument identity is still the larger
bottleneck than approximate onset timing.

## What changed

V19 uses four aligned probability views:

1. the v18 stacked ensemble on the separated drum stem;
2. a rights-cleared-data focal specialist on the drum stem;
3. the v18 ensemble on the original mixture; and
4. the focal specialist on the original mixture.

Each drum class has a frozen convex blend, confidence threshold, and temporal
non-maximum-suppression distance. The mixture view restores information that
separation removes; the stem view suppresses accompaniment leakage. The
weak-class specialist snapshot was produced before this benchmark from a
Groove/E-GMD/FreePats experiment. Its retained best state is the
validation-recalibrated resume snapshot because later focal-loss epochs did not
beat it. No RWC audio was added to model training.

The decoder was calibrated on the opened first 50 RWC songs and frozen in
`groove-multiview-articulation-v19.json` before any audio from the remaining 39
songs was downloaded, separated, inferred, or scored. The holdout gain therefore
measures the fixed policy rather than post-test tuning.

## Generalization by drum-production type

The table combines both partitions and compares identical songs at ±50 ms.

| RWC drum source | Songs | v18 detailed F1 | v19 detailed F1 | Gain |
| --- | ---: | ---: | ---: | ---: |
| Live drums | 21 | 45.24% | 61.07% | +15.83 pp |
| Drum loops | 8 | 24.60% | 40.23% | +15.63 pp |
| Drum sequences | 60 | 52.19% | 63.06% | +10.87 pp |

Loops remain the weakest category despite the improvement. The 89-song
per-track detailed F1 median is 64.31%; 33 songs are at least 70%, 16 are at
least 80%, and 8 remain below 30%.

## Remaining instrument failures

Combined 89-song detailed metrics at ±50 ms:

| Instrument | Reference hits | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| Kick | 2,790 | 80.58% | 82.11% | 81.34% |
| Closed hi-hat | 4,145 | 55.73% | 78.02% | 65.02% |
| Snare | 2,305 | 62.99% | 61.65% | 62.31% |
| Cross-stick | 83 | 42.65% | 69.88% | 52.97% |
| Crash | 326 | 67.97% | 26.69% | 38.33% |
| Open hi-hat | 651 | 37.52% | 37.17% | 37.35% |
| Floor tom | 138 | 54.29% | 13.77% | 21.97% |
| High tom | 29 | 23.08% | 10.34% | 14.29% |
| Ride | 81 | 15.00% | 3.70% | 5.94% |
| Low tom | 90 | 0.00% | 0.00% | 0.00% |
| Mid tom | 82 | 0.00% | 0.00% | 0.00% |
| Pedal hi-hat | 201 | 0.00% | 0.00% | 0.00% |
| Ride bell | 101 | 0.00% | 0.00% | 0.00% |
| Tambourine | 1,432 | 0.00% | 0.00% | 0.00% |

The current micro-optimized candidate deliberately suppresses rare classes whose
false alarms were worse than emitting no events. That improves the overall
score but is not acceptable as the final all-instrument product. Tambourine,
detailed toms, pedal hi-hat, ride, and ride bell need natural, commercially
licensed training and validation recordings before launch.

## Integrity and claim boundary

- Source corpus: RWC 2.0 Popular Music Database and aligned RWC annotations.
- License: CC BY-NC 4.0, local non-commercial research only.
- Selection: deterministic SHA-256 ranking. The first 50 tracks are development;
  the remaining 39 eligible tracks are the holdout. The partitions are disjoint.
- Inputs: 20-second full-mixture excerpts; 1,780 scored seconds total.
- References: 12,454 aligned GM percussion events mapped to DrumScribe's 14
  detailed classes.
- Pipeline: original mixture plus `htdemucs_ft` drum stem into fixed v19 fusion.
- Matching: class-aware one-to-one onset matching at ±20 ms and ±50 ms.
- The RWC audio/annotations, Demucs stems, raw predictions, and full local reports
  remain gitignored and are not redistributed.
- The compact evidence contains no source audio, MIDI, or track-level reference
  annotations.

The holdout is now opened and cannot be reused as fresh evidence. The v19
decoder itself is also non-commercial because its thresholds were calibrated
against CC BY-NC annotations. It is a validated research direction, not a
sellable checkpoint.

## Reproduction

```bash
# First 50 opened development songs
uv run --project ml python scripts/run_rwc_popular_50_benchmark.py prepare
uv run --project ml python scripts/run_rwc_popular_50_benchmark.py separate
PYTHONPATH=ml/src:scripts uv run --project ml python \
  scripts/run_rwc_multiview_benchmark.py

# Remaining 39 songs, selected without overlap
uv run --project ml python scripts/run_rwc_popular_50_benchmark.py prepare \
  --data-root data/research-corpus/rwc-popular-holdout-39-v1 \
  --track-count 39 --selection-offset 50
uv run --project ml python scripts/run_rwc_popular_50_benchmark.py separate \
  --data-root data/research-corpus/rwc-popular-holdout-39-v1
PYTHONPATH=ml/src:scripts uv run --project ml python \
  scripts/run_rwc_multiview_benchmark.py \
  --data-root data/research-corpus/rwc-popular-holdout-39-v1 \
  --output output/rwc-popular-holdout-39-v19/benchmark-result.json
```

Compact committed evidence is in
`docs/benchmarks/data/RWC_POPULAR_MULTIVIEW_V19.json`.

## Next production accuracy work

The evidence supports keeping the multi-view architecture. The next checkpoint
must be trained and calibrated only on commercially compatible, natural
full-mixture/stem pairs with explicit coverage for the five suppressed
articulation groups. It must then be evaluated once on a newly acquired,
rights-cleared, untouched corpus. A 90% selling claim remains blocked until that
fresh product-level evaluation actually reaches the threshold.
