# Groove architecture pilot

Date: 2026-08-30

Decision: advance `spectral_moe` to a scaled licensed-data experiment; do not ship either pilot

## Purpose

This experiment compares DrumScribe's original CRNN with its clean-room sparse
spectral mixture-of-experts architecture. It is an architecture screen, not a
production-quality claim or a release-gate evaluation.

## Controls

- Source: Groove MIDI Dataset 1.0.0, CC BY 4.0.
- Selection: deterministic SHA-256 ranking of complete source-prescribed groups.
- Scope: 100 training groups and 20 validation groups.
- Test isolation: all 122 official test recordings were excluded and remain unopened.
- Prepared dataset SHA-256: `769531a9e9e1291d671020d2957385fcdea961151ba34bb15b9abc718abe92c9`.
- Shared settings: seed `20260830`, three epochs, hidden width 64, batch size 8,
  1,024-frame windows, learning rate 0.0003, dropout 0.2 and two-frame onset tolerance.
- Thresholds were selected on validation data. These results therefore must not be
  presented as held-out generalization performance.

## Results

| Metric | CRNN control | Spectral MoE | Change |
| --- | ---: | ---: | ---: |
| Trainable parameters | 244,540 | 508,992 | +108.1% |
| Best validation macro F1 | 0.597 | 0.674 | +0.078 (+13.0%) |
| Epoch 1 macro F1 | 0.530 | 0.572 | +0.042 |
| Epoch 2 macro F1 | 0.567 | 0.655 | +0.088 |
| Epoch 3 macro F1 | 0.597 | 0.674 | +0.078 |

Best-epoch per-class validation F1:

| Class | CRNN | Spectral MoE | Change |
| --- | ---: | ---: | ---: |
| Kick | 0.749 | 0.722 | -0.027 |
| Snare | 0.835 | 0.856 | +0.021 |
| Cross-stick | 0.952 | 0.951 | -0.001 |
| Closed hi-hat | 0.454 | 0.496 | +0.042 |
| Open hi-hat | 0.495 | 0.691 | +0.196 |
| Pedal hi-hat | 0.244 | 0.368 | +0.123 |
| Ride | 0.268 | 0.322 | +0.054 |
| Ride bell | 0.244 | 0.479 | +0.234 |
| Crash | 0.400 | 0.754 | +0.354 |
| High tom | 0.860 | 0.886 | +0.026 |
| Mid tom | 0.866 | 0.750 | -0.116 |
| Floor tom | 0.795 | 0.819 | +0.025 |
| Low tom | no support | no support | blocked |
| Tambourine | no support | no support | blocked |

The macro scores above average only the 12 classes with validation support. The
release gate averages all 14 supported product classes and treats missing evidence
as failure, so these figures cannot satisfy the release gate.

## Decision and next experiment

Advance the sparse-expert architecture because it improves the controlled macro
score and materially helps cymbal/hi-hat articulation. Do not promote the pilot
checkpoint: its kick and mid-tom results regressed, ride/hi-hat scores remain weak,
and low tom/tambourine have no source examples.

The next training experiment must add rights-cleared one-shot overlays for low tom,
tambourine and articulation balancing to training records only. After that smoke
test passes, run the same architecture on E-GMD using dedicated x86/Linux training
compute, tune exclusively on validation, and open the held-out test split once for
the documented 0.99 release gate.
