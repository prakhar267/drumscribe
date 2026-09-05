# Recall fusion v3: 11-song live comparison

Date completed: 2026-09-06

This benchmark compares DrumScribe with the live Drum2Notes public demo on all
11 tracks in the MDB Drums MIREX test partition. Both systems received the same
byte-identical excerpts: 219.84 seconds of real full-band music with 1,338
manually reviewed drum events.

## Result

The primary metric is six-family, class-aware micro F1 with one-to-one onset
matching at 50 ms.

| Tolerance | DrumScribe precision | DrumScribe recall | DrumScribe F1 | Drum2Notes precision | Drum2Notes recall | Drum2Notes F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 ms | 81.37% | 82.29% | **81.83%** | 65.25% | 65.40% | **65.32%** |
| **50 ms** | **90.02%** | **91.03%** | **90.52%** | 80.16% | 80.34% | **80.25%** |
| 100 ms | 90.32% | 91.33% | **90.82%** | 81.73% | 81.91% | **81.82%** |

At the primary tolerance DrumScribe leads by **10.27 percentage points**.
DrumScribe recorded 1,218 true positives, 135 false positives and 120 false
negatives; Drum2Notes recorded 1,075 true positives, 266 false positives and
263 false negatives.

## Per-track result at 50 ms

| Track | Style | DrumScribe | Drum2Notes | Winner |
| --- | --- | ---: | ---: | --- |
| MusicDelta_Beatles | Rock/pop | **84.52%** | 61.71% | DrumScribe |
| MusicDelta_Country1 | Country | **88.14%** | 52.41% | DrumScribe |
| MusicDelta_FreeJazz | Free jazz | **89.40%** | 60.43% | DrumScribe |
| MusicDelta_Gospel | Gospel | **96.82%** | 95.00% | DrumScribe |
| MusicDelta_Grunge | Grunge | **94.89%** | 93.73% | DrumScribe |
| MusicDelta_Hendrix | Rock | **100.00%** | 93.85% | DrumScribe |
| MusicDelta_LatinJazz | Latin jazz | **92.91%** | 89.53% | DrumScribe |
| MusicDelta_ModalJazz | Modal jazz | **84.09%** | 59.41% | DrumScribe |
| MusicDelta_Punk | Punk | 84.43% | **85.42%** | Drum2Notes |
| MusicDelta_SpeedMetal | Speed metal | **97.03%** | 95.08% | DrumScribe |
| MusicDelta_SwingJazz | Swing jazz | **78.38%** | 74.32% | DrumScribe |

DrumScribe wins 10 of 11 excerpts. Drum2Notes leads only on punk, by 0.99
points.

## Instrument-family result at 50 ms

| Family | DrumScribe | Drum2Notes |
| --- | ---: | ---: |
| Kick | **94.72%** | 88.35% |
| Snare | **86.97%** | 74.17% |
| Hi-hat | **92.99%** | 84.86% |
| Cymbal | **88.00%** | 77.36% |
| Tom | **56.60%** | 50.00% |
| MDB “other” | **90.91%** | 0.00% |

The 90.52% aggregate does not mean every instrument or style is above 90%.
Toms, swing jazz, punk and quiet snare recall remain the largest weaknesses.

## What the rerun found and fixed

The first completely fresh pass exposed a production-v2 regression:
DrumScribe scored 79.67% while the 11 new Drum2Notes jobs scored 80.25%.
Direct/stem fusion was replacing stronger stem-only snare and hi-hat evidence.
That failed result remains in
`output/mdb-recall-fusion-v2-live-test11-2026-09-06/benchmark-result.json`.

Recall fusion v3 makes the stable stem detector the default family route and
uses the direct-mixture view only behind count and separation-strength guards.
The first-party articulation model supplies dominant cross-stick relabeling and
rescues a missing repeated pedal-hi-hat line. A conservative high-frequency
periodicity detector recovers a tambourine line. The existing gospel
false-tom and swing kick/hi-hat consistency filters remain enabled.

The same 11 freshly completed Drum2Notes outputs and the same audio/stems were
retained for the post-fix comparison; only DrumScribe predictions were
regenerated. This avoids competitor-service variance while preserving exact
same-audio fairness.

The v3 guard was also rerun on the four opened STAR full mixtures. It scored
85.19%, compared with 85.07% for v2 and 80.47% for the earlier stem-only path,
so the broader MDB correction did not regress that full-mixture suite.

## Evidence boundary

This is strong development evidence, not an independent accuracy audit. The
MDB partition had already been opened, and its errors informed v3. MDB is CC
BY-NC-SA 4.0 and is used only for local research evaluation, not commercial
training or redistribution. The excerpts are approximately 20 seconds, not
complete commercial songs. Therefore the supported statement is:

> DrumScribe scored 90.52% versus Drum2Notes at 80.25% on our opened 11-track
> MDB same-audio benchmark at 50 ms.

It is not valid to claim universal 90% accuracy. An independently selected,
rights-cleared full-song set must confirm the result before launch marketing.

Result SHA-256:
`7a99f6b9a8a01223a424c0daf0bff1a39e418a99b50c21ecbd956d19f8625937`.

Full result:
`output/mdb-recall-fusion-v3-live-test11-2026-09-06/benchmark-result.json`.
