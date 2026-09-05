# 100 real-song excerpts: DrumScribe v6 vs Drum2Notes

Run date: 6 September 2026 (IST)

## Result

On the same 100 full-mixture, 20-second excerpts, DrumScribe v6 reached
**78.72% five-family micro F1 at ±50 ms**, compared with **78.34% for v5** and
**71.39% for the live Drum2Notes public demo**. DrumScribe won 85 excerpts,
Drum2Notes won 13, and two were tied.

| Tolerance | V6 precision | V6 recall | V6 F1 | V5 F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| ±20 ms | 63.74% | 66.17% | **64.93%** | 64.59% | 38.91% |
| ±50 ms | 77.27% | 80.23% | **78.72%** | 78.34% | 71.39% |
| ±100 ms | 79.65% | 82.70% | **81.15%** | 80.73% | 75.76% |

The gain is small but consistent at all three tolerances. At ±50 ms, v6
removes 168 false positives while losing 30 true positives, raising precision
by 0.96 points and lowering recall by 0.22 points.

| Split | V5 F1 | V6 F1 | Change |
| --- | ---: | ---: | ---: |
| Songs 1–50, development | 76.05% | **76.64%** | +0.59 points |
| Songs 51–100, already-open secondary evidence | 80.85% | **80.99%** | +0.14 points |

The second half is not a sealed holdout. It had already been opened during
earlier releases and was inspected during v6 safety refinement. Its result is
useful regression evidence, not an independent generalization estimate.

## What changed

V6 keeps v5 unchanged for kick, snare, hi-hat and cymbal. It adds a guarded,
stem-strength-adaptive tom decoder:

- the separated-drum-to-mixture RMS ratio chooses one of three development-
  selected tom peak rules;
- low-strength stems use 75% stem / 25% direct-mixture evidence, while the
  other two ranges use the stem alone;
- the adaptive route is allowed only if the v5 pipeline already found at least
  one tom, preventing the new decoder from inventing tom parts on unsupported
  songs; and
- 61 of 100 songs changed in the tom family. Fresh v5/v6 output comparison
  found zero changes in kick, snare, hi-hat or cymbal events.

The tom family improved from **44.34% to 48.67% F1** across all 100 songs.

## Development discipline and rejected experiments

The adaptive-rule search evaluated direct/stem weights, activation thresholds,
peak contexts and RMS partitions on songs 1–50. Five-fold rule selection raised
out-of-fold development micro F1 from 76.05% to 76.45%. The full development
rule reached 76.64% after the conservative baseline-hit guard.

A compact learned fusion model combined direct and separated ADTOF activations,
temporal context, stem strength and the independent articulation stream. It was
rejected before secondary evaluation because its five-fold out-of-fold score
was **72.47%**, 3.58 points below v5. New kick, snare, hi-hat and cymbal rules
also failed the out-of-fold selection and were discarded. Prior YourMT3+ and
Inverse Drum Machine experiments remained below the selected ADTOF pipeline.

## Dataset and family results

| Dataset | Excerpts | V5 F1 | V6 F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: | ---: |
| MDB Drums | 11 | 90.10% | **90.20%** | 81.35% |
| RWC Popular | 89 | 76.95% | **77.36%** | 70.26% |

| Family | V5 F1 | V6 F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: |
| Kick | **86.43%** | **86.43%** | 79.92% |
| Snare | **76.50%** | **76.50%** | 69.22% |
| Hi-hat | **78.25%** | **78.25%** | 72.71% |
| Cymbal | **67.96%** | **67.96%** | 52.93% |
| Tom | 44.34% | **48.67%** | 38.19% |

Tom remains the weakest family and the main reason the broad result is not 90%.

## All represented styles

The 11 MDB styles have only one excerpt each, so those rows are examples rather
than stable genre estimates.

| Style | Excerpts | DrumScribe v6 F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: |
| J-pop | 70 | **77.47%** | 70.06% |
| Pop | 19 | **76.94%** | 71.02% |
| Country | 1 | **80.00%** | 59.84% |
| Free jazz | 1 | **89.50%** | 60.43% |
| Gospel | 1 | **96.82%** | 95.00% |
| Grunge | 1 | **95.59%** | 93.73% |
| Latin jazz | 1 | **91.96%** | 89.53% |
| Modal jazz | 1 | **85.55%** | 59.41% |
| Punk | 1 | 82.86% | **85.42%** |
| Rock | 1 | **99.61%** | 93.85% |
| Rock/pop | 1 | **81.54%** | 68.79% |
| Speed metal | 1 | **97.03%** | 95.08% |
| Swing jazz | 1 | **80.00%** | 74.32% |

By drum-source type, DrumScribe scored 80.43% on 32 live-drum excerpts, 79.95%
on 60 sequenced-drum excerpts, and 62.97% on eight loop-based excerpts.

## Protocol and limits

- Inputs: 89 RWC Popular excerpts plus all 11 MDB Drums test songs; 100 unique
  hashes and 2,000 seconds of full musical mixtures.
- Metric: one-to-one, class-aware onset matching over kick, snare, hi-hat, tom
  and cymbal at ±20, ±50 and ±100 ms.
- DrumScribe: 100 fresh v6 predictions using hash-validated `htdemucs_ft` stems.
- Competitor: 100 retained live Drum2Notes responses, reused only after every
  source-audio hash matched.

This is an opened local research benchmark, not a sealed independent audit.
The evidence supports “78.72% five-family onset F1 on this benchmark, versus
71.39% for Drum2Notes.” It does not support “90% on arbitrary songs” or “90%
complete notation accuracy.”

## Evidence and reproduction

The compact committed report is
`docs/benchmarks/data/REAL_SONG_100_V6_VS_DRUM2NOTES.json`. Full local evidence
is under `output/real-song-100-v6-vs-drum2notes-2026-09-06/`.

```bash
PYTHONPATH='scripts/model_runners:scripts:packages/music-engine/src:ml/src' \
  .research-models/adtof-env/bin/python \
  scripts/run_real_song_100_live_benchmark.py \
  --workers 3 --device cpu \
  --reuse-drum2notes-from \
  output/real-song-100-v5-vs-drum2notes-2026-09-06
```

Integrity hashes:

- Full report: `30fcaea6fdaa6db3fc138aaf79d4438809db62a5e59b56ef484f56e268d6df61`
- RWC development selection: `20e0f3c39d3d41cd0e822e678a941da11fe0135b268748f0c67fe61cd3f36451`
- RWC secondary selection: `3e1608e17f92d89e533e9bcb17e3b8b9fe06cf57d619e8c3e3f2c42f1fec2f0a`
- V6 configuration: `c8bd5795cfc12b9acf170c8e7a2980f7e899d459733047ed65a77c0a6ecdc11d`
- Compact report: `af3beba2d0f5bbc48dc32b6ec47a16affb4e1edd3f20f20e1d20a26c66a68d47`
