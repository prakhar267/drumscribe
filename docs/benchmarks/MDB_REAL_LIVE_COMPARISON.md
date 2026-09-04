# Real full-mixture Drum2Notes comparison

Date completed: 2026-09-05

This benchmark measures actual full-band music rather than isolated drums. Four
predeclared 20-second MDB Drums excerpts cover country, free jazz, grunge and
speed metal. The source performances are real, the mixes include the other
instruments, and the references are MDB's manually reviewed drum annotations.

## Result

The primary metric is six-family, class-aware micro F1 with one-to-one onset
matching at 50 ms.

| System | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| DrumScribe current app research beta (`htdemucs_ft` -> `drumscribe-hybrid-v1`) | 73.93% | 79.08% | **76.42%** |
| Klangio Drum2Notes live public demo | 76.66% | 83.01% | **79.71%** |
| DrumScribe best research path (`htdemucs_ft` -> ADTOF) | 89.20% | 89.98% | **89.59%** |

The current app path trails Drum2Notes by 3.29 percentage points on this probe.
The best research path exceeds Drum2Notes by 9.88 points, but it is 0.41 points
below 90% and is not commercially deployable because ADTOF is non-commercial
and the selected Demucs checkpoint rights remain unresolved.

## Per-genre F1 at 50 ms

| Genre | References | Current app | Drum2Notes | Best research |
| --- | ---: | ---: | ---: | ---: |
| Country | 59 | **77.36%** | 52.41% | 65.04% |
| Free jazz | 114 | 57.14% | 60.43% | **88.89%** |
| Grunge | 136 | 72.67% | 93.73% | **94.51%** |
| Speed metal | 150 | 91.30% | 95.08% | **95.68%** |
| Aggregate | 459 | 76.42% | 79.71% | **89.59%** |

All four Drum2Notes jobs completed. No track or service failure was removed.
Both products started from the exact same WAV bytes; sample-level verification
also confirmed that each excerpt is exactly the first 20 seconds of its source
full mix. DrumScribe separation was rerun from those submitted excerpts rather
than reusing a stem generated from a longer file.

The run also exposed and fixed a local integration problem: the hybrid command
in `.env` pointed to an ML environment without PyTorch. It now uses the API's
working inference environment with the repository packages on `PYTHONPATH`.
The process-isolated app adapter was then exercised successfully and reproduced
47 hits for the country excerpt.

At the stricter 20 ms tolerance, current DrumScribe scores 67.37%, Drum2Notes
64.02%, and the best research path 78.52%. At 100 ms they score 76.63%, 81.38%
and 90.24%, respectively. This timing sensitivity is why the 50 ms metric is
kept as the primary comparison instead of selecting the most favorable window.

## Boundary

This is 80 seconds across four tracks, not a market-wide accuracy audit. MDB
Drums is CC BY-NC-SA 4.0 and is used for research only. The MIREX split was also
opened during prior development, so it is not a fresh sealed test. These results
must not be described as “90% production accuracy.”

The reproducible runner is
`scripts/run_drum2notes_mdb_real_benchmark.py`. It retains the live service
responses, source and prediction hashes, per-track event counts, failure states,
and 20/50/100 ms scores in
`output/mdb-real-live-comparison-2026-09-05/benchmark-result.json`.
