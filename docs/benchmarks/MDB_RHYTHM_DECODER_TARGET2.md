# Gospel and swing-jazz rhythm-decoder improvement

Date completed: 2026-09-05

The 11-track live benchmark showed Drum2Notes ahead on gospel and swing jazz.
The production ADTOF runner now applies two bounded, audio-result-derived
consistency rules before returning hits:

- Suppress a long, highly regular tom-only intro when it ends before any other
  detected kit activity. This targets pitched accompaniment misclassified as
  toms.
- On a detected slow-swing pattern, suppress hi-hat hits that collide with the
  steady kick pulse. This preserves the offbeat swing hi-hat while removing
  duplicate kick-aligned detections.

The rules use only model output timing. They do not read a genre label,
reference annotation, filename or competitor output.

## Final fresh live result

Both songs were separated and transcribed again from their original full-mix
WAVs. Two new live Drum2Notes jobs were submitted from the same byte-identical
audio, and both completed. The primary metric is six-family, class-aware micro
F1 with one-to-one onset matching at 50 ms.

| Track | System | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: |
| Gospel | **DrumScribe** | **93.75%** | 98.68% | **96.15%** |
| Gospel | Drum2Notes | 90.48% | **100.00%** | 95.00% |
| Swing jazz | **DrumScribe** | **87.88%** | **70.73%** | **78.38%** |
| Swing jazz | Drum2Notes | 83.33% | 67.07% | 74.32% |

DrumScribe now leads by **1.15 points on gospel** and **4.05 points on swing
jazz**. Across the two tracks together, DrumScribe scores **87.50%** versus
Drum2Notes at **85.06%**.

## Regression checks

- The independent 12-track MDB training partition selected no global threshold
  replacement; the candidate global calibration was rejected because it
  reduced wider test accuracy.
- The new consistency rules triggered on none of those 12 training tracks.
- On a newly separated 11-track test batch, the rules triggered only for
  gospel and swing jazz. Comparable aggregate F1 improved from 86.59% to
  87.57%; the decoded events for the other nine tracks were unchanged.
- Unit tests cover both correction patterns and an ordinary rock pattern that
  must remain unchanged.

## Evidence boundary

The gospel and swing labels were inspected to diagnose these errors, so this
post-fix target result is development evidence, not an independent sealed
holdout. A new cross-dataset gospel/swing set is still required for a broad
marketing claim.

The full live result is
`output/mdb-rhythm-decoder-target2-live-2026-09-05/benchmark-result.json`, with
SHA-256
`361376172219a5a073e7fe8e4c002b02b627249c9de601069c686ba880332d8c`.
