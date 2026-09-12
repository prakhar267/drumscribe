# Oracle fast-separator production gate

Run date: 13 September 2026 (IST)

## Decision

Use the hash-pinned single `htdemucs` model on the Oracle Always Free worker.
Retain `htdemucs_ft` as the rollback quality ensemble. This keeps processing
fully hosted on Oracle; no founder laptop, payment method, or paid compute is
part of the runtime.

## Same-input performance result

The exact same 36.373515-second rights-cleared `funk-108` mixture was separated
inside the production worker container on the 4-OCPU/24-GB Ampere A1 VM.

| Configuration | Separation time | Change from current ensemble |
| --- | ---: | ---: |
| `htdemucs_ft`, production-equivalent default | 134s | baseline |
| `htdemucs_ft --jobs 4` | 133s | 0.7% faster; rejected |
| `htdemucs`, all four Oracle cores | **37s** | **72.4% faster** |

The forced `--jobs 4` output also differed by 3.79% relative RMS while saving
only one second, so that setting was rejected. A lower-overlap, single-core
experiment was stopped after it exceeded the untouched production runtime and
is not a release candidate.

The local Apple M4 comparison completed the same HTDemucs-ft separation in
31.08 seconds using MPS. The selected Oracle result is six seconds slower on
this clip and does not require the laptop to remain online.

## Full notation check

The frozen 105-second launch set contains two real human Groove MIDI Dataset
performances combined with rights-cleared musical backing. Both complete mixes
were re-separated with `htdemucs` on Oracle, transcribed with unchanged recall
fusion v6, and scored against the aligned reference events.

| Track | Audio | Oracle separation | Transcription | End-to-end model stages | Fast F1 at 50ms | Quality-ensemble F1 at 50ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| rock-groove8-65 | 45s | 41s | 14s | 55s | 66.09% | 65.82% |
| funk-108 | 60s | 55s | 15s | 70s | 59.53% | 59.89% |
| Aggregate | 105s | — | — | 125s | **61.47%** | **61.64%** |

Aggregate five-family F1 deltas were -0.59 point at 20ms, -0.17 point at 50ms,
and -0.28 point at 100ms. The selected trade reduces same-input separation time
by 72.4% for a 0.17-point F1 change at the product's 50ms comparison tolerance.

## Boundaries

- This is a small, rights-cleared production gate, not a general accuracy
  percentage or independent audit.
- The unchanged recall-fusion decoder was developed with HTDemucs-ft stems.
  Wider post-launch monitoring must compare edit rates and failures by recorded
  separation model version.
- The exact `htdemucs` checkpoint SHA-256 is
  `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`.
- Founder-reported commercial permission was reaffirmed for this exact model on
  13 September 2026. The private underlying grant remains an external legal
  evidence requirement before paid launch.

## Live production verification

Commit `30ebf31` was deployed to the Oracle worker with
`DRUMSCRIBE_DEMUCS_MODEL=htdemucs`. The rebuilt image verified the checkpoint
hash during the build, loaded the model with network access disabled, passed the
production provider-safety gate, and started Celery with zero restarts.

A fresh anonymous user flow uploaded the 45-second rights-cleared rock mix
through the public `https://drumtoscore.com/api/v1` proxy. Job
`82047208-0d1b-409c-a73d-94a1e2a68930` reached `READY` without retries or an
error. It recorded separation provider version `demucs-isolated-v5/htdemucs`.

| Production stage | Seconds |
| --- | ---: |
| Validation | 7.5714 |
| Normalization | 8.3091 |
| Drum separation | **46.8065** |
| Transcription | 33.2509 |
| Beat detection | 9.4301 |
| Quantization | 4.5418 |
| Score generation | 5.5302 |
| Finalization | 3.7880 |

Worker start-to-finish time was 126.15 seconds; queue submission-to-ready time
was 137.36 seconds. Public readiness remained HTTP 200 after the run. The exact
test project was then soft-deleted. Database verification showed its project
deletion timestamp and all five derived assets marked for recoverable deletion;
no customer project or object was read, modified, or deleted.
