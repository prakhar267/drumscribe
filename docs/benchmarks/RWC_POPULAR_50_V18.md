# RWC Popular 50-song full-mixture benchmark

Date completed: 2026-09-04

## Result

DrumScribe v18 processed all 50 selected songs and reached **46.48% detailed
event micro F1**, **53.27% six-family micro F1**, and **58.99% core
kick/snare/hi-hat micro F1 at ±50 ms**. This is the first current-v18 test in
this repository that combines a broad set of professionally produced popular
music, real full mixtures, source separation, and aligned performance MIDI.

The result does **not** support “90% accurate on popular songs” or “ready to sell
at 90% accuracy.” The earlier 90%+ v18 results measure isolated drum recordings,
whereas this result includes errors introduced by full-song source separation
and the domain shift from training drums to mastered popular music.

## Overall metrics

| Metric | ±20 ms | ±50 ms |
| --- | ---: | ---: |
| Detailed 14-class precision | 24.66% | 40.69% |
| Detailed 14-class recall | 32.85% | 54.19% |
| **Detailed 14-class F1** | **28.17%** | **46.48%** |
| Six-family F1 | 32.86% | 53.27% |
| Core kick/snare/hi-hat F1 | 36.42% | 58.99% |
| Class-agnostic onset F1 | 46.19% | 69.81% |

The class-agnostic onset score is substantially higher than the detailed score.
This means that many rhythmic onsets are near the correct time, but the system
often assigns the wrong drum instrument or adds extra hits.

Across individual songs, detailed F1 has a mean of 48.36%, median of 46.53%,
minimum of 1.01%, and maximum of 86.62%. Three songs exceed 80%, nine exceed
70%, and eight are below 30%.

## Results by drum-production type

| Drum source in RWC metadata | Songs | Detailed F1 | Family F1 | Core F1 |
| --- | ---: | ---: | ---: | ---: |
| Live drums | 14 | 43.87% | 49.70% | 56.25% |
| Drum loops | 7 | 22.08% | 30.24% | 37.29% |
| Drum sequences | 29 | 53.86% | 60.77% | 64.90% |

| Singing language | Songs | Detailed F1 | Family F1 | Core F1 |
| --- | ---: | ---: | ---: | ---: |
| English | 11 | 48.57% | 54.05% | 58.34% |
| Japanese | 39 | 45.95% | 53.08% | 59.16% |

The largest production-type failure is loop-based drums. Language has little
effect, which is expected for a drum detector and suggests that the dominant
problem is drum timbre/mix production rather than vocals' language.

## Detailed instrument failures

| Instrument | Reference hits | Precision | Recall | F1 at ±50 ms |
| --- | ---: | ---: | ---: | ---: |
| Kick | 1,643 | 50.70% | 90.63% | 65.02% |
| Snare | 1,392 | 36.68% | 62.93% | 46.35% |
| Closed hi-hat | 2,396 | 59.78% | 52.67% | 56.00% |
| Open hi-hat | 376 | 34.98% | 48.94% | 40.80% |
| Pedal hi-hat | 122 | 1.85% | 13.93% | 3.26% |
| Cross-stick | 63 | 36.92% | 76.19% | 49.74% |
| Crash | 151 | 50.00% | 29.14% | 36.82% |
| Ride | 61 | 20.00% | 6.56% | 9.88% |
| Ride bell | 71 | 0.00% | 0.00% | 0.00% |
| High tom | 16 | 5.63% | 25.00% | 9.20% |
| Mid tom | 42 | 6.67% | 9.52% | 7.84% |
| Low tom | 13 | 0.00% | 0.00% | 0.00% |
| Floor tom | 58 | 7.67% | 58.62% | 13.57% |
| Tambourine | 915 | 0.00% | 0.00% | 0.00% |

Tambourine is unusually important in this corpus and is absent from v18's
validated training support. It contributes 12.5% of all reference events, but
removing it would not repair the much lower 58.99% core score. Kick has high
recall but low precision, and snares, cymbals, tom identity, and hi-hat
articulations all need material improvement.

## All 50 song results

The primary columns below are class-aware, one-to-one event micro F1 at ±50 ms.

| # | Track | Drum source | Detailed F1 | Family F1 | Core F1 |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | RWC_P003 — HORO | sequences | 36.67% | 36.67% | 36.67% |
| 2 | RWC_P004 — Spice of Life | sequences | 47.50% | 50.00% | 50.96% |
| 3 | RWC_P005 — Koino Ver.2.4 | sequences | 55.98% | 60.68% | 65.13% |
| 4 | RWC_P006 — Funky Life | sequences | 30.61% | 54.51% | 55.67% |
| 5 | RWC_P009 — Doukoku | live | 37.46% | 49.50% | 48.09% |
| 6 | RWC_P013 — Catch ball | sequences | 41.06% | 59.60% | 62.17% |
| 7 | RWC_P015 — old fashioned | sequences | 40.93% | 46.63% | 52.33% |
| 8 | RWC_P017 — Anata to aete | sequences | 62.30% | 69.79% | 69.95% |
| 9 | RWC_P019 — COOL Motion | sequences | 24.19% | 36.80% | 55.67% |
| 10 | RWC_P020 — Tokimeki no syunkan | sequences | 48.15% | 51.85% | 51.61% |
| 11 | RWC_P021 — Feeling In My Heart | sequences | 50.76% | 60.91% | 75.16% |
| 12 | RWC_P022 — Koi ni ochiru jikan ni kansuru kousatsu | sequences | 70.03% | 74.80% | 75.60% |
| 13 | RWC_P025 — tell me | sequences | 46.15% | 57.53% | 59.31% |
| 14 | RWC_P026 — aozora sanpo michi | sequences | 56.45% | 63.98% | 71.53% |
| 15 | RWC_P027 — stay | sequences | 40.24% | 40.24% | 40.24% |
| 16 | RWC_P030 — syounen no omoi | sequences | 64.32% | 70.27% | 71.04% |
| 17 | RWC_P031 — Moving Round and Round | loops | 10.97% | 21.45% | 27.18% |
| 18 | RWC_P033 — DREAM MAGIC | sequences | 72.00% | 73.45% | 76.38% |
| 19 | RWC_P034 — Hitoyo no yume | live | 22.91% | 30.17% | 29.20% |
| 20 | RWC_P035 — Midarana kami no moushigo | live | 33.75% | 35.62% | 47.27% |
| 21 | RWC_P036 — over and over | live | 36.36% | 49.01% | 55.96% |
| 22 | RWC_P038 — 1999 | live | 54.79% | 54.79% | 73.39% |
| 23 | RWC_P039 — SPUL | sequences | 86.62% | 90.45% | 94.04% |
| 24 | RWC_P040 — promise | sequences | 85.64% | 87.26% | 87.50% |
| 25 | RWC_P042 — Fly to the moon | sequences | 29.37% | 44.98% | 60.05% |
| 26 | RWC_P043 — Centimeter no kodoku | sequences | 77.46% | 80.28% | 81.93% |
| 27 | RWC_P044 — REAL na 5 hun | sequences | 72.69% | 76.85% | 79.13% |
| 28 | RWC_P045 — Hajimari | live | 42.91% | 53.09% | 53.91% |
| 29 | RWC_P049 — Sekai no mikata | sequences | 28.97% | 33.56% | 35.96% |
| 30 | RWC_P055 — First Love | live | 76.64% | 77.57% | 77.07% |
| 31 | RWC_P056 — I've got a mail | loops | 21.51% | 40.86% | 47.11% |
| 32 | RWC_P057 — Stay with me | sequences | 46.90% | 52.41% | 53.15% |
| 33 | RWC_P058 — Silver shoes | loops | 1.01% | 1.01% | 0.00% |
| 34 | RWC_P059 — Tenshi no utatane | loops | 24.20% | 34.25% | 48.81% |
| 35 | RWC_P060 — Kumorizora | loops | 32.13% | 36.07% | 42.47% |
| 36 | RWC_P062 — Be with me Now | sequences | 71.53% | 72.99% | 74.35% |
| 37 | RWC_P063 — Power of mind | live | 58.86% | 62.03% | 64.03% |
| 38 | RWC_P067 — Tokei no hayasa wa | live | 55.32% | 60.99% | 63.16% |
| 39 | RWC_P068 — Nichiyoubi | live | 58.43% | 68.91% | 70.92% |
| 40 | RWC_P081 — How Deep Is Your Love? | sequences | 67.91% | 74.63% | 74.24% |
| 41 | RWC_P084 — Someday | live | 42.11% | 50.42% | 51.03% |
| 42 | RWC_P087 — I think of you | sequences | 64.71% | 65.69% | 65.35% |
| 43 | RWC_P088 — Woman Like You | live | 40.78% | 42.20% | 57.56% |
| 44 | RWC_P093 — Sweet Dreams | sequences | 56.20% | 64.46% | 64.46% |
| 45 | RWC_P094 — Life | sequences | 66.24% | 70.06% | 69.28% |
| 46 | RWC_P095 — Feel | live | 37.21% | 41.28% | 47.48% |
| 47 | RWC_P096 — Weekend | loops | 38.04% | 42.39% | 42.31% |
| 48 | RWC_P097 — Don't Lie To Me | sequences | 86.27% | 87.39% | 87.39% |
| 49 | RWC_P098 — 31 BLUES | live | 32.80% | 44.62% | 47.10% |
| 50 | RWC_P100 — No Regrets | loops | 31.85% | 43.31% | 47.06% |

## Corpus and protocol

- Source: [RWC Music Database v2 on Zenodo](https://zenodo.org/records/18656623).
  The release describes RWC as copyright-cleared research music, licenses it
  under CC BY-NC 4.0, and includes 100 Popular Music subset recordings.
- Reference: [RWC 2.0 annotations](https://github.com/rwc-music/rwc-annotations)
  at commit `0a1a6c31dbe73a7f5d44f7caef8cd0999402a4c2`. The repository identifies
  RWC-P's preprocessed MIDI as aligned and supplies manual music start/end
  metadata.
- Selection: exclude the 10 RWC-P rows marked `Without drums`; rank the other
  90 by SHA-256 of `drumscribe-rwc-popular-50-v1:RWCID`; take 50; report in
  RWC ID order.
- Window: 20 seconds beginning one second before the first supported GM drum
  event, bounded by the manual music start/end annotations. This is a
  reference-assisted but fixed active-window rule; it does not inspect model
  predictions.
- Inputs: 50 full-mixture excerpts, not isolated drums; 1,000 seconds total.
- Pipeline: `htdemucs_ft` two-stem drum separation followed by frozen
  `groove-stacked-articulation-v18` with eight hash-pinned checkpoints.
- Reference events: 7,319 channel-10 GM percussion onsets converted to the 14
  DrumScribe detailed labels.
- Matching: class-aware, one-to-one onset matching at ±20 ms and ±50 ms.
- Training separation: RWC was not used to train or tune v18. Now that this
  benchmark has been opened, it must not be used to tune v18 and later called
  sealed evidence.

These are popular-style research recordings, not Billboard, Spotify, or market
popularity-ranked songs. Testing famous commercial masters would require
legally acquired audio and licensed authoritative drum scores. No commercial
audio or sheet music was pirated for this benchmark.

## Integrity audit

- All 50 clips are exactly 20 seconds and have unique SHA-256 records.
- All 50 separated `drums.wav` files exist, are exactly 20 seconds, and have
  hash records.
- All raw v18 outputs are hash-recorded per track.
- A complete replay produced identical 50 prediction hashes, aggregate scores,
  and group scores.
- Timing-offset audit found a median per-track best absolute shift of only
  40 ms. A single global -20 ms diagnostic changed detailed F1 by just +0.62
  percentage points, so a broad alignment error does not explain the result.
- Frozen selection/reference SHA-256:
  `81cdb70d9f6f5fa53c1c1d2c035bad5a9cce545c06b2f33ef65584a980389aca`.
- Selection manifest SHA-256:
  `20e0f3c39d3d41cd0e822e678a941da11fe0135b268748f0c67fe61cd3f36451`.
- Separation manifest SHA-256:
  `4d755a14cb40ce2466642fe1fb7cd69fa93c11a15b57a8ed66e80cfdaa571425`.
- Full local result SHA-256:
  `c1c7c35a0917182a73badc7ae2c731f79646658da16278c13b7840c5f3b31687`.

Compact committed evidence is in
`docs/benchmarks/data/RWC_POPULAR_50_V18.json`. Licensed audio, MIDI, separated
stems, feature caches, and the full local result remain ignored under `data/`
and `output/` and are not redistributed.

## Reproduction

```bash
git clone https://github.com/rwc-music/rwc-annotations \
  data/research-corpus/rwc-annotations

uv run --project ml python scripts/run_rwc_popular_50_benchmark.py \
  prepare --workers 4

uv run --project ml python scripts/run_rwc_popular_50_benchmark.py separate

uv run --project ml --extra train python \
  scripts/run_rwc_popular_50_benchmark.py evaluate --device auto
```

## Product decision and next accuracy work

Keep the 90% claim restricted to the exact isolated-drum benchmarks where it
was measured. Do not use it for arbitrary uploaded songs.

The next model-development benchmark must be separate from these 50 opened
songs. The strongest evidence-based priorities are full-mixture augmentation,
train-only examples of mastered loops and live kits, explicit tambourine and
ride-bell support, separation-aware hard negatives to reduce kick/snare false
positives, and a commercially licensed separator. Improvements must then be
evaluated on a new frozen song set that was not used for selection or tuning.
