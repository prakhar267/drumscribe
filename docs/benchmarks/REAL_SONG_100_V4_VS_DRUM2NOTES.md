# 100 real-song excerpts: DrumScribe v4 vs Drum2Notes

Run date: 6 September 2026 (IST)

## Result

On the same 100 full-mixture, 20-second song excerpts, DrumScribe v4 reached
**78.05% five-family micro F1 at ±50 ms**, compared with **71.39% for the live
Drum2Notes public demo**. DrumScribe won 84 excerpts, Drum2Notes won 14, and
two were tied.

| Tolerance | DrumScribe precision | DrumScribe recall | DrumScribe F1 | Drum2Notes precision | Drum2Notes recall | Drum2Notes F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ±20 ms | 62.63% | 66.42% | **64.47%** | 36.61% | 41.51% | 38.91% |
| ±50 ms | 75.83% | 80.41% | **78.05%** | 67.18% | 76.16% | 71.39% |
| ±100 ms | 78.23% | 82.97% | **80.53%** | 71.29% | 80.83% | 75.76% |

This is a measured improvement over the same v3 run: 77.05% to 78.05%
overall. The 50-song verification half, whose labels were not used to choose
the new rules, improved from 79.63% to 80.61%.

| Split | Role | v3 F1 | v4 F1 | Change |
| --- | --- | ---: | ---: | ---: |
| Songs 1–50 | Decoder selection | 74.69% | **75.73%** | +1.05 points |
| Songs 51–100 | Separate verification | 79.63% | **80.61%** | +0.98 points |

## What changed

V4 adds a deterministic confidence-and-consensus gate after the existing
direct-mixture, Demucs-stem, and first-party articulation routes have fused.
A weak snare, tom, hi-hat, or cymbal detection is retained only when the
independent articulation route finds the same family nearby. Strong detections
are unchanged, and kick is intentionally excluded because gating it reduced
verification recall.

Compared with v3 across all 100 songs, v4 removed 693 predicted events while
losing 141 true positives. This raised precision from 72.99% to 75.83%, while
recall changed from 81.58% to 80.41%. Constant latency shifts, whole-route
family switching, and a Groove-trained hit classifier were evaluated and
rejected because they did not transfer as well to the separate verification
half.

## Dataset and instrument results

| Dataset | Excerpts | v3 F1 | v4 F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: | ---: |
| MDB Drums | 11 | 90.10% | **90.08%** | 81.35% |
| RWC Popular | 89 | 75.55% | **76.64%** | 70.26% |

MDB is effectively flat, with a 0.02-point decrease; the broader RWC portion
improves by 1.09 points. V4 is therefore an overall improvement, not a claim
that every subset improved.

| Family | v3 F1 | v4 F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: |
| Kick | 86.30% | **86.30%** | 79.92% |
| Snare | 75.69% | **76.00%** | 69.22% |
| Hi-hat | 77.29% | **77.91%** | 72.71% |
| Cymbal | 62.83% | **67.96%** | 52.93% |
| Tom | 40.73% | **44.34%** | 38.19% |

Cymbals and toms receive the largest relative gains, but tom transcription at
44.34% remains the largest model weakness. V4 does not meet a 90% general-song
accuracy target.

## All represented styles

The 11 MDB styles have one excerpt each, so their rows are examples rather
than stable genre estimates.

| Style | Excerpts | DrumScribe v4 F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: |
| J-pop | 70 | **76.47%** | 70.06% |
| Pop | 19 | **77.31%** | 71.02% |
| Country | 1 | **80.00%** | 59.84% |
| Free jazz | 1 | **87.32%** | 60.43% |
| Gospel | 1 | **96.82%** | 95.00% |
| Grunge | 1 | **95.24%** | 93.73% |
| Latin jazz | 1 | **93.53%** | 89.53% |
| Modal jazz | 1 | **84.57%** | 59.41% |
| Punk | 1 | 82.86% | **85.42%** |
| Rock | 1 | **100.00%** | 93.85% |
| Rock/pop | 1 | **80.30%** | 68.79% |
| Speed metal | 1 | **97.03%** | 95.08% |
| Swing jazz | 1 | **80.00%** | 74.32% |

By drum-source type, DrumScribe scored 80.01% on 32 live-drum excerpts, 79.44%
on 60 sequenced-drum excerpts, and 60.70% on eight loop-based excerpts.
Drum2Notes scored 74.92%, 72.62%, and 50.32%, respectively.

## Protocol and limits

- Inputs: 89 RWC Popular excerpts plus all 11 songs in the MDB Drums MIREX
  test partition; 100 unique audio hashes and 2,000 seconds total.
- Audio: full musical mixtures, never isolated drum tracks. Both products
  received the exact same WAV bytes.
- References: aligned RWC General MIDI drum parts and manually reviewed MDB
  class annotations.
- Metric: class-aware one-to-one onset matching for kick, snare, hi-hat, tom,
  and cymbal. Exact simultaneous reference notes in one family count once.
- DrumScribe: 100 fresh v4 predictions with hash-validated `htdemucs_ft` stems.
- Competitor: the 100 successful live Drum2Notes responses from the identical
  frozen v3 inputs were reused only after each source-audio hash was checked.

This remains an opened, local research comparison rather than a sealed
third-party audit. The RWC and MDB licenses restrict the evaluation material to
research use, so the audio and annotations are not committed or redistributed.
Some RWC references have sparse coverage or a global alignment offset; every
selected item remains in the result after inspection.

The evidence supports the narrow claim “78.05% five-family onset F1 on this
100-excerpt benchmark, versus 71.39% for Drum2Notes.” It does not support “90%
on arbitrary songs” or “90% complete notation accuracy.”

## Evidence and reproduction

The committed compact report is
`docs/benchmarks/data/REAL_SONG_100_V4_VS_DRUM2NOTES.json`. Full local results
and raw responses are under
`output/real-song-100-v4-vs-drum2notes-2026-09-06/`.

```bash
PYTHONPATH='scripts/model_runners:scripts:packages/music-engine/src:ml/src' \
  .research-models/adtof-env/bin/python \
  scripts/run_real_song_100_live_benchmark.py \
  --workers 3 --device cpu \
  --reuse-drum2notes-from \
  output/real-song-100-v3-vs-drum2notes-2026-09-06
```

Integrity hashes:

- Full report: `7f28174afd604a7e41cba4731ad4110ed1a3ba33a62be9dbb67230c3131446e5`
- Selection manifest: `652e9c56b101e6aef17948eafa5bd396a39373e487bfb7eb68ded246c233a37c`
- V4 configuration: `8c0785c431740d84cdbabe2d973e50712d088d5085355e3cdd35f6ebdc4572f1`
