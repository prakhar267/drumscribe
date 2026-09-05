# New cross-genre live comparison

Date completed: 2026-09-05

DrumScribe and Klangio Drum2Notes were rerun on 24 newly selected inputs that
did not appear in the earlier ten- or 100-recording live comparisons. Both
systems received the same PCM WAV bytes. All 24 new Drum2Notes jobs completed,
so the result contains no competitor failures.

The primary metric is five-family, class-aware micro F1 with one-to-one onset
matching at 50 ms. The five evaluated families are kick, snare, hi-hat, tom and
cymbal.

## Result

| Category | Inputs | DrumScribe | Drum2Notes | DrumScribe lead |
| --- | ---: | ---: | ---: | ---: |
| Heavy rock / punk | 5 | **82.56%** | 76.31% | **+6.25 points** |
| Pop / soul | 5 | **85.04%** | 72.95% | **+12.09 points** |
| Funk / hip-hop | 5 | **89.02%** | 87.09% | **+1.93 points** |
| Jazz / world | 5 | **82.31%** | 75.93% | **+6.38 points** |
| STAR full mixtures | 4 | **80.47%** | 59.85% | **+20.62 points** |
| **All 24 inputs** | **24** | **84.34%** | **75.91%** | **+8.43 points** |

DrumScribe won every aggregate category and 18 of 24 individual inputs.

| Tolerance | DrumScribe | Drum2Notes |
| --- | ---: | ---: |
| 20 ms | **81.02%** | 49.04% |
| 50 ms | **84.34%** | 75.91% |
| 100 ms | **84.59%** | 81.48% |

At 50 ms, DrumScribe produced 2,766 true positives, 106 false positives and
921 false negatives. Drum2Notes produced 2,523 true positives, 437 false
positives and 1,164 false negatives. DrumScribe's mean matched-hit timing error
was 7.98 ms versus 17.63 ms for Drum2Notes.

## Per-family result at 50 ms

| Family | DrumScribe | Drum2Notes |
| --- | ---: | ---: |
| Kick | **94.78%** | 83.31% |
| Snare | **79.61%** | 70.13% |
| Hi-hat | **84.00%** | 77.51% |
| Toms | **79.12%** | 74.25% |
| Cymbals | **78.40%** | 63.35% |

## Frozen selection and systems

The selection manifest was written before either system ran. Its SHA-256 is
`3272f4c36490e1955631c196419853e9a6744c85684048df9e2b25f32b8df87c`.
Selection used source metadata and a fixed hash seed, not reference events or
model results. No input was removed or replaced after inference.

The 20 Groove inputs contain five recordings per broad category and 19 named
styles: rock, progressive rock, halftime rock, rockabilly, funk-rock, soft pop,
Motown, disco, blues shuffle, pop, funk, hip-hop, funk-Latin, breakbeat,
Brazilian Latin, Middle Eastern, reggae, New Orleans cha-cha and chacarera.
DrumScribe used `ADTOF-pytorch -> rhythm-consistency-v1` for these drum-only
uploads.

The four STAR Drums preview items are full musical mixtures. DrumScribe used
`htdemucs_ft -> ADTOF-pytorch -> rhythm-consistency-v1`. STAR provides aligned
references for re-synthesized drums mixed with real melodic and vocal
recordings. The official preview archive MD5 was verified as
`1feacdce05f963db0e6ce1d3a5aa35fc` before extraction.

Drum2Notes used its live public demo with the `solo` model and all drum notes.
The audio-aligned MusicJSON consumed by its result viewer was scored. All 24
jobs returned state `ok`.

## Evidence boundary

This is strong same-audio development evidence, not proof of accuracy on every
genre or an independent sealed audit.

- The Groove recordings are real professional or semi-professional human drum
  performances captured from a Roland TD-11. They are not complete commercial
  songs. Groove is CC BY 4.0.
- STAR mixes contain real musician backing/vocals, but the annotated drum stem
  is re-synthesized. STAR preview audio has source-specific Creative Commons
  terms and is used here only for local research evaluation.
- The selected ADTOF weights were not changed during this test. Other retired
  first-party research models in this repository used the Groove training
  split, so this is not organization-wide unseen data.
- Four balanced style families plus a four-item full-mix preview are broad
  coverage, not literally every musical genre.
- The result does not justify a universal 90% marketing claim. The overall
  score is 84.34%, and the lowest individual DrumScribe score is 64.45%.

Official dataset descriptions: [Groove MIDI Dataset](https://magenta.withgoogle.com/datasets/groove)
and [STAR Drums](https://zenodo.org/records/15690078).

Raw result:
`output/novel-cross-genre-live-v1-2026-09-05/benchmark-result.json`, SHA-256
`c5d01972df4a02f23160e08fc08c1d214d5b5f88993cddb15f9d30fd7e68aaf4`.
