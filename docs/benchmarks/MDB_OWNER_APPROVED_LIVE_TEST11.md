# Eleven-track real-music DrumScribe versus Drum2Notes benchmark

Date completed: 2026-09-05

This follow-up expands the four-excerpt live probe to all 11 tracks in the MDB
Drums MIREX test partition. It covers 219.84 seconds of real full-band audio
and 1,338 manually annotated drum events. DrumScribe regenerated every
`htdemucs_ft` stem and ADTOF prediction. Eleven new live Drum2Notes jobs were
submitted from the same byte-identical WAV inputs, and all 11 completed.

## Aggregate result

The primary metric is six-family, class-aware micro F1 with one-to-one onset
matching at 50 ms.

| Tolerance | DrumScribe precision | DrumScribe recall | DrumScribe F1 | Drum2Notes precision | Drum2Notes recall | Drum2Notes F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 ms | 75.13% | 75.64% | **75.38%** | 65.25% | 65.40% | **65.32%** |
| **50 ms** | **86.27%** | **86.85%** | **86.55%** | **80.16%** | **80.34%** | **80.25%** |
| 100 ms | 86.64% | 87.22% | **86.93%** | 81.73% | 81.91% | **81.82%** |

DrumScribe leads Drum2Notes by **6.30 percentage points** at 50 ms.

## Per-track F1 at 50 ms

| Track | Genre/style | DrumScribe | Drum2Notes | Winner |
| --- | --- | ---: | ---: | --- |
| MusicDelta_Beatles | Rock/pop | 64.63% | 61.71% | DrumScribe |
| MusicDelta_Country1 | Country | 64.52% | 52.41% | DrumScribe |
| MusicDelta_FreeJazz | Free jazz | 88.79% | 60.43% | DrumScribe |
| MusicDelta_Gospel | Gospel | 87.21% | 95.00% | Drum2Notes |
| MusicDelta_Grunge | Grunge | 94.89% | 93.73% | DrumScribe |
| MusicDelta_Hendrix | Rock | 100.00% | 93.85% | DrumScribe |
| MusicDelta_LatinJazz | Latin jazz | 92.68% | 89.53% | DrumScribe |
| MusicDelta_ModalJazz | Modal jazz | 78.06% | 59.41% | DrumScribe |
| MusicDelta_Punk | Punk | 84.32% | 85.42% | Drum2Notes |
| MusicDelta_SpeedMetal | Speed metal | 97.03% | 95.08% | DrumScribe |
| MusicDelta_SwingJazz | Swing jazz | 71.60% | 74.32% | Drum2Notes |

DrumScribe wins 8 of 11 tracks. Drum2Notes wins gospel, punk and swing jazz.

## Instrument-family result at 50 ms

| Family | DrumScribe F1 | Drum2Notes F1 |
| --- | ---: | ---: |
| Kick | **94.99%** | 88.35% |
| Hi-hat | **88.43%** | 84.86% |
| Cymbal | **85.99%** | 77.36% |
| Snare | **85.20%** | 74.17% |
| Tom | 42.86% | **50.00%** |
| Other | 0.00% | 0.00% |

Toms, MDB's `OTHER` category, country, Beatles-style mixes and swing jazz are
the clearest remaining weaknesses.

Post-benchmark update: the rhythm-consistency decoder subsequently improved
gospel from 87.21% to 96.15% and swing jazz from 71.60% to 78.38% on a fresh
same-audio live rerun, exceeding Drum2Notes on both. See
`MDB_RHYTHM_DECODER_TARGET2.md`. Because those labels informed diagnosis, the
post-fix numbers are development evidence rather than a sealed holdout.

## Decision and evidence boundary

The wider test does not reproduce the four-track probe's 90.69% score.
DrumScribe still beats Drum2Notes overall, but **86.55% is the more useful live
competitor benchmark for launch planning** because it covers more styles and
over three times as much audio. It does not support a general 90% claim.

This remains an opened, non-sealed research benchmark from one dataset. MDB is
CC BY-NC-SA 4.0 and was used only for internal evaluation, not production
training. A genuinely independent cross-dataset test remains desirable.

The complete result is in
`output/mdb-owner-approved-live-test11-2026-09-05/benchmark-result.json`, with
SHA-256
`7f1ae0db760ade232907e6a22bd783756cb769374417fa8de14f81f94a3e6b35`.
