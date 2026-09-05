# Owner-approved DrumScribe versus Drum2Notes live rerun

Date completed: 2026-09-05 IST

DrumScribe and the live Klangio Drum2Notes public demo were tested again on
the same four real full-band MDB Drums excerpts used in the earlier comparison.
Both systems received the same byte-identical 20-second WAV for each track.
All DrumScribe Demucs stems and ADTOF predictions were regenerated, and four
new Drum2Notes job IDs were submitted. All four competitor jobs completed.

## Result

The primary metric is six-family, class-aware micro F1 with one-to-one onset
matching at 50 ms across 459 manually annotated events.

| Tolerance | DrumScribe precision | DrumScribe recall | DrumScribe F1 | Drum2Notes precision | Drum2Notes recall | Drum2Notes F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 ms | 78.92% | 79.96% | **79.44%** | 61.57% | 66.67% | **64.02%** |
| **50 ms** | **90.11%** | **91.29%** | **90.69%** | **76.66%** | **83.01%** | **79.71%** |
| 100 ms | 90.75% | 91.94% | **91.34%** | 78.27% | 84.75% | **81.38%** |

DrumScribe leads Drum2Notes by **10.99 percentage points** at the primary
50 ms tolerance.

## Per-song F1 at 50 ms

| Track | Genre | DrumScribe | Drum2Notes | DrumScribe lead |
| --- | --- | ---: | ---: | ---: |
| MusicDelta_Country1 | Country | 67.23% | 52.41% | +14.81 pp |
| MusicDelta_FreeJazz | Free jazz | 90.35% | 60.43% | +29.93 pp |
| MusicDelta_Grunge | Grunge | 94.89% | 93.73% | +1.16 pp |
| MusicDelta_SpeedMetal | Speed metal | 96.37% | 95.08% | +1.29 pp |

At 50 ms, DrumScribe's kick F1 is 95.27%, hi-hat 94.24%, cymbal 89.80%
and snare 89.74%. The 18 reference events in MDB's unsupported `OTHER`
family were all missed. Country remains the clearest weakness.

## Reproducibility and claim boundary

The four input-audio hashes match the earlier live comparison exactly. The
new Drum2Notes job IDs returned byte-identical MusicJSON to the earlier run,
so its 79.71% score reproduced exactly. DrumScribe moved from 89.59% to 90.69%
because Demucs' default one-shift stabilization uses a random time shift and
produced new stem bytes; the transcription model and thresholds were unchanged.

This fresh run crosses 90% on this narrow four-excerpt probe. It does **not**
establish 90% accuracy across arbitrary real music. The wider 11-track MDB
full-mixture rerun remains 82.99% at 50 ms, and the four excerpts are from an
opened, non-sealed research split. MDB is CC BY-NC-SA 4.0 and was used only for
internal research evaluation.

A subsequent same-audio live comparison expanded this probe to all 11 MDB test
tracks. DrumScribe scored 86.55% versus Drum2Notes at 80.25%. See
`MDB_OWNER_APPROVED_LIVE_TEST11.md`.

The complete result is in
`output/mdb-owner-approved-live-rerun-2026-09-05/benchmark-result.json`, with
SHA-256
`b7cd530ee33c327c8793dc6ac2241dbe4aeebc5b15e803a4e1c780285b1ea029`.
The reusable fresh-run command is
`scripts/run_owner_approved_drum2notes_mdb_comparison.py`.
