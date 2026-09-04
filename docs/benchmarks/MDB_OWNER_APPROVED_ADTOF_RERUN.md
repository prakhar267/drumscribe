# Owner-approved ADTOF real-music rerun

Date completed: 2026-09-05

DrumScribe's self-hosted `htdemucs_ft` -> ADTOF-pytorch path was regenerated
from all 11 original MDB Drums MIREX full mixtures after commercial approval
`OWNER-ATTESTATION-2026-09-05` was recorded. No cached stem or prediction was
used. Each temporary stem was deleted after transcription, while its SHA-256
was retained in the report.

## Aggregate result

The primary metric remains six-family, class-aware micro F1 with one-to-one
onset matching at 50 ms.

| Tolerance | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| 20 ms | 77.45% | 71.89% | 74.57% |
| **50 ms** | **86.20%** | **80.01%** | **82.99%** |
| 100 ms | 86.33% | 80.14% | 83.12% |

The fresh 82.99% result reproduces the earlier 82.98% run within 0.02
percentage points. Commercial authorization therefore changes whether the
pipeline can be deployed; it does not change the model's accuracy.

## Per-track F1 at 50 ms

| Track | F1 |
| --- | ---: |
| MusicDelta_Beatles | 63.09% |
| MusicDelta_Country1 | 64.45% |
| MusicDelta_FreeJazz | 79.78% |
| MusicDelta_Gospel | 94.12% |
| MusicDelta_Grunge | 91.76% |
| MusicDelta_Hendrix | 100.00% |
| MusicDelta_LatinJazz | 83.19% |
| MusicDelta_ModalJazz | 79.19% |
| MusicDelta_Punk | 87.28% |
| MusicDelta_SpeedMetal | 94.12% |
| MusicDelta_SwingJazz | 70.54% |

At 50 ms, kick reaches 95.15% F1, cymbal 84.87%, snare 82.43%, hi-hat
77.70%, tom 31.37%, and MDB's `other` family 0%. Country side-stick, swing,
Beatles-style mixes, toms and the `other` taxonomy remain the main accuracy
gaps. The system is commercially authorized, but this benchmark still does not
support a broad “90% accurate” claim.

## Evidence boundary

MDB Drums is CC BY-NC-SA 4.0 and is used only for internal research evaluation.
The MIREX test split was opened previously, so this is a reproducibility rerun,
not a fresh sealed audit. Test annotations were not used for training,
threshold selection or calibration during this run.

The reusable runner is `scripts/run_owner_approved_adtof_mdb.py`. The complete
local report, per-track hashes and predictions are in
`output/mdb-owner-approved-adtof-rerun-2026-09-05/benchmark-result.json`; its
SHA-256 is
`e5379f8ef05e16e6303334d72959d1987413da082efd9cc0c0782a79c911248a`.
