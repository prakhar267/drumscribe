# 100 real-song excerpts: DrumScribe v3 vs Drum2Notes

Run date: 6 September 2026 (IST)

## Result

On the same 100 full-mixture, 20-second song excerpts, production DrumScribe
v3 reached **77.05% five-family micro F1 at ±50 ms**, compared with
**71.39% for the live Drum2Notes public demo**. DrumScribe won 79 excerpts,
Drum2Notes won 19, and two were tied.

| Tolerance | DrumScribe precision | DrumScribe recall | DrumScribe F1 | Drum2Notes precision | Drum2Notes recall | Drum2Notes F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ±20 ms | 60.24% | 67.33% | **63.59%** | 36.61% | 41.51% | **38.91%** |
| ±50 ms | 72.99% | 81.58% | **77.05%** | 67.18% | 76.16% | **71.39%** |
| ±100 ms | 75.33% | 84.19% | **79.51%** | 71.29% | 80.83% | **75.76%** |

The 90% result from the earlier 11-song MDB comparison is reproduced inside
this larger run: DrumScribe scores 90.10% on MDB. The broader RWC Popular
portion scores 75.55%, bringing the properly weighted 100-song result to
77.05%.

| Dataset | Excerpts | DrumScribe F1 | Drum2Notes F1 | DrumScribe lead |
| --- | ---: | ---: | ---: | ---: |
| MDB Drums | 11 | **90.10%** | 81.35% | +8.76 points |
| RWC Popular | 89 | **75.55%** | 70.26% | +5.29 points |

## Instrument families

| Family | DrumScribe F1 | Drum2Notes F1 |
| --- | ---: | ---: |
| Kick | **86.30%** | 79.92% |
| Hi-hat | **77.29%** | 72.71% |
| Snare | **75.69%** | 69.22% |
| Cymbal | **62.83%** | 52.93% |
| Tom | **40.73%** | 38.19% |

Tom identification and cymbal precision remain the largest technical gaps.
They are hidden by any headline number that reports only kick/snare/hi-hat.

## All 13 declared styles

These are every style represented by the frozen suite. “All genres” here means
all represented categories, not every genre in existence. The 11 MDB styles
have only one excerpt each, so those rows are useful examples rather than
stable genre estimates.

| Style | Excerpts | DrumScribe F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: |
| J-pop | 70 | **75.27%** | 70.06% |
| Pop | 19 | **76.56%** | 71.02% |
| Country | 1 | **80.00%** | 59.84% |
| Free jazz | 1 | **89.40%** | 60.43% |
| Gospel | 1 | **96.82%** | 95.00% |
| Grunge | 1 | **94.89%** | 93.73% |
| Latin jazz | 1 | **92.91%** | 89.53% |
| Modal jazz | 1 | **84.09%** | 59.41% |
| Punk | 1 | 84.43% | **85.42%** |
| Rock | 1 | **100.00%** | 93.85% |
| Rock/pop | 1 | **80.30%** | 68.79% |
| Speed metal | 1 | **97.03%** | 95.08% |
| Swing jazz | 1 | **78.38%** | 74.32% |

By drum-source type, DrumScribe scored 79.56% on 32 live-drum excerpts,
78.12% on 60 sequenced-drum excerpts, and 60.18% on eight loop-based excerpts.
Drum2Notes scored 74.92%, 72.62%, and 50.32%, respectively.

## Protocol

- Inputs: 89 RWC Popular excerpts plus all 11 songs in the MDB Drums MIREX
  test partition; 100 unique audio hashes and 2,000 seconds total.
- Audio: full musical mixtures, never isolated drum tracks. Both products
  received the exact same WAV bytes.
- References: aligned RWC General MIDI drum parts and manually reviewed MDB
  class annotations.
- Metric: class-aware one-to-one onset matching for kick, snare, hi-hat, tom,
  and cymbal. Exact simultaneous reference notes in one family count once.
- DrumScribe: fresh `drumscribe-recall-fusion-v3` inference using hash-validated
  cached `htdemucs_ft` stems from those exact excerpts.
- Competitor: 100 fresh and unique live Drum2Notes jobs using “solo / all drum
  notes”; all 100 returned successfully.
- Failure policy: any missing competitor result remains in the denominator as
  zero predictions. No failures occurred in this run.

## Important limits

This is an opened development comparison, not a sealed third-party audit. Both
datasets restrict this audio/annotation evaluation to research use, so their
audio is not committed or redistributed. RWC Popular includes live, sequenced,
and looped drum parts. Some RWC references visibly have sparse coverage or a
global alignment offset; both products score near zero on the same affected
items. The report retains those items instead of removing them after seeing
the results.

Therefore this run supports the statement “77.05% five-family onset F1 on this
100-excerpt opened benchmark, versus 71.39% for the live Drum2Notes demo.” It
does not support “90% on arbitrary songs,” “all genres are solved,” or “90%
complete notation accuracy.”

## Evidence and reproduction

The committed compact report is
`docs/benchmarks/data/REAL_SONG_100_V3_VS_DRUM2NOTES.json`. It contains every
item's input hash, F1, winner, category, and event counts. The full local report
and all raw service responses are under
`output/real-song-100-v3-vs-drum2notes-2026-09-06/`.

```bash
PYTHONPATH='ml/src:packages/music-engine/src:scripts' \
  .research-models/adtof-env/bin/python \
  scripts/run_real_song_100_live_benchmark.py --workers 3 --device cpu
```

To recompute metrics from the retained raw evidence without submitting new
jobs:

```bash
PYTHONPATH='ml/src:packages/music-engine/src:scripts' \
  .research-models/adtof-env/bin/python \
  scripts/run_real_song_100_live_benchmark.py --score-only
```
