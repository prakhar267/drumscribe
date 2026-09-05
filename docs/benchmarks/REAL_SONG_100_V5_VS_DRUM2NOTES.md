# 100 real-song excerpts: DrumScribe v5 vs Drum2Notes

Run date: 6 September 2026 (IST)

## Result

On the same 100 full-mixture, 20-second excerpts, DrumScribe v5 reached
**78.34% five-family micro F1 at ±50 ms**, compared with **71.39% for the live
Drum2Notes public demo**. DrumScribe won 84 excerpts, Drum2Notes won 14, and
two were tied.

| Tolerance | DrumScribe precision | DrumScribe recall | DrumScribe F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: | ---: |
| ±20 ms | 62.92% | 66.35% | **64.59%** | 38.91% |
| ±50 ms | 76.31% | 80.47% | **78.34%** | 71.39% |
| ±100 ms | 78.65% | 82.93% | **80.73%** | 75.76% |

V5 improves the identical v4 run from 78.05% to 78.34%. More importantly,
the separate 50-song verification half improved from 80.61% to 80.85%.

| Split | Role | v4 F1 | v5 F1 | Change |
| --- | --- | ---: | ---: | ---: |
| Songs 1–50 | Decoder selection | 75.73% | **76.05%** | +0.32 points |
| Songs 51–100 | Separate verification | 80.61% | **80.85%** | +0.24 points |

## What changed

V5 keeps v4's confidence-and-consensus gate and improves the lower-level peak
fusion:

- weak-stem kick fusion now trusts the separated stem fully, uses a higher
  activation threshold, and measures a shorter local peak context;
- snare fusion uses more separated-stem weight, a lower activation threshold,
  and a shorter peak context to preserve quiet strikes; and
- the normal hi-hat stem route uses a higher activation threshold with a
  longer adaptive-average window to reject bleed without deleting the
  repeated pattern.

The development search also found a rule that suppressed many toms and raised
the development headline. It was rejected because verification tom F1 fell
from 59.72% to 42.38%. A development-trained hit classifier, articulation-only
recovery, and timestamp replacement were rejected for the same transfer-first
reason.

## Dataset and family results

| Dataset | Excerpts | v4 F1 | v5 F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: | ---: |
| MDB Drums | 11 | 90.08% | **90.10%** | 81.35% |
| RWC Popular | 89 | 76.64% | **76.95%** | 70.26% |

| Family | v4 F1 | v5 F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: |
| Kick | 86.30% | **86.43%** | 79.92% |
| Snare | 76.00% | **76.50%** | 69.22% |
| Hi-hat | 77.91% | **78.25%** | 72.71% |
| Cymbal | **67.96%** | **67.96%** | 52.93% |
| Tom | **44.34%** | **44.34%** | 38.19% |

Tom transcription remains the largest weakness and is the clearest reason the
general real-song score is not yet 90%.

## All represented styles

The 11 MDB styles have only one excerpt each, so their rows are examples, not
stable genre estimates.

| Style | Excerpts | DrumScribe v5 F1 | Drum2Notes F1 |
| --- | ---: | ---: | ---: |
| J-pop | 70 | **76.93%** | 70.06% |
| Pop | 19 | **77.05%** | 71.02% |
| Country | 1 | **80.00%** | 59.84% |
| Free jazz | 1 | **89.50%** | 60.43% |
| Gospel | 1 | **96.82%** | 95.00% |
| Grunge | 1 | **95.24%** | 93.73% |
| Latin jazz | 1 | **91.96%** | 89.53% |
| Modal jazz | 1 | **85.55%** | 59.41% |
| Punk | 1 | 82.86% | **85.42%** |
| Rock | 1 | **99.61%** | 93.85% |
| Rock/pop | 1 | **80.30%** | 68.79% |
| Speed metal | 1 | **97.03%** | 95.08% |
| Swing jazz | 1 | **80.00%** | 74.32% |

By drum-source type, DrumScribe scored 80.28% on 32 live-drum excerpts, 79.74%
on 60 sequenced-drum excerpts, and 60.88% on eight loop-based excerpts.

## Protocol and limits

- Inputs: 89 RWC Popular excerpts plus all 11 MDB Drums test songs; 100 unique
  input hashes and 2,000 seconds total.
- Audio: full musical mixtures. Both products received the same WAV bytes.
- Metric: one-to-one class-aware onset matching over kick, snare, hi-hat, tom,
  and cymbal at ±20, ±50, and ±100 ms.
- DrumScribe: 100 fresh v5 predictions with hash-validated `htdemucs_ft` stems.
- Competitor: 100 previously successful live Drum2Notes responses, reused only
  after checking each identical source-audio hash.

This is an opened local research benchmark, not a sealed independent audit.
RWC and MDB evaluation material is not committed or redistributed. Sparse or
globally offset RWC references remain in the score after inspection.

The evidence supports “78.34% five-family onset F1 on this benchmark, versus
71.39% for Drum2Notes.” It does not support “90% on arbitrary songs” or “90%
complete notation accuracy.”

## Evidence and reproduction

The compact report is
`docs/benchmarks/data/REAL_SONG_100_V5_VS_DRUM2NOTES.json`. Full local evidence
is under `output/real-song-100-v5-vs-drum2notes-2026-09-06/`.

```bash
PYTHONPATH='scripts/model_runners:scripts:packages/music-engine/src:ml/src' \
  .research-models/adtof-env/bin/python \
  scripts/run_real_song_100_live_benchmark.py \
  --workers 3 --device cpu \
  --reuse-drum2notes-from \
  output/real-song-100-v4-vs-drum2notes-2026-09-06
```

Integrity hashes:

- Full report: `933364e7b60bb57c6ecec72c90b2f68f11a3fda864d5e05bf730900f22712377`
- Selection manifest: `fdbf5db6e72562391ab909357026c9deb53464dc82937bdc4cf80a955beb395f`
- V5 configuration: `6e62bcc15b741d440209fd12fc4634fc723fdfade0bc816c5b7eb8bbf6f82e13`
