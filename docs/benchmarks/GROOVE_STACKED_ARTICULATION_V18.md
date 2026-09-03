# Confidence-gated hi-hat conflict decoder v18

Date completed: 2026-09-04

Decision: **accept v18 as the stronger self-hosted isolated-drum detector.** It
keeps the v17 checkpoint stack and adds a conservative decoder for physically
exclusive hi-hat articulations. When closed, open, or pedal hi-hat all produce
a peak on the exact same frame, the decoder removes the losing labels only if
the winner leads the runner-up by at least 1.25 normalized log-odds. Ambiguous
events remain unchanged.

This is post-selection detector evidence on isolated drums. It does not measure
full-song source separation, quantization, notation spelling, page layout, or
export accuracy, and it is not evidence of 90% accuracy on arbitrary music.

## Accepted results

| Evaluation | Metric | v17 | v18 | Change |
| --- | --- | ---: | ---: | ---: |
| Groove validation, 120 records | Supported macro F1 | 89.7135% | **89.7541%** | +0.0406 pp |
| Groove validation, 120 records | Micro F1 | 90.0291% | **90.0820%** | +0.0529 pp |
| Groove genre benchmark, 100 records | Detailed micro F1 at 50 ms | 91.8925% | **91.9506%** | +0.0580 pp |
| Groove genre benchmark, 100 records | Six-family micro F1 at 50 ms | 92.5190% | **92.5776%** | +0.0587 pp |
| Groove + E-GMD opened multi-kit test, 122 records | Supported macro F1 | 89.3850% | **89.4412%** | +0.0562 pp |
| Groove + E-GMD opened multi-kit test, 122 records | Micro F1 | 89.9282% | **90.0016%** | +0.0734 pp |

The affected articulation classes all improve on both broad comparisons:

| Evaluation | Class | v17 | v18 | Change |
| --- | --- | ---: | ---: | ---: |
| 100-record genre | Closed hi-hat | 94.3055% | **94.3222%** | +0.0167 pp |
| 100-record genre | Open hi-hat | 76.0331% | **76.3485%** | +0.3155 pp |
| 100-record genre | Pedal hi-hat | 69.7400% | **70.2768%** | +0.5368 pp |
| 122-record multi-kit | Closed hi-hat | 92.5077% | **92.5497%** | +0.0420 pp |
| 122-record multi-kit | Open hi-hat | 80.1508% | **80.2773%** | +0.1265 pp |
| 122-record multi-kit | Pedal hi-hat | 70.3065% | **70.8127%** | +0.5061 pp |

Three of four genre groups improve. Heavy rock/punk changes from 95.1748% to
95.1714% (-0.0034 percentage points): one true pedal-hat event and one false
pedal-hat event were removed on different tracks. The global closed/open/pedal
scores and both aggregate metrics improve.

## Rejected experiments

- A full family-first decoder reduced hi-hat articulation F1 and was rejected.
- Applying competition to ride/ride-bell caused a class regression and was
  rejected; v18 does not alter that family.
- Two focal-loss fine-tuning epochs reduced standalone validation macro F1 from
  87.21% at the resumed checkpoint to 86.74% and 86.40%. Those weights were not
  added to v18. The optional focal objective remains backward compatible for a
  future from-scratch experiment.

## Reproducibility

- Frozen config: `ml/configs/groove-stacked-articulation-v18.json`
- Config SHA-256:
  `72348715dfee13de8caabb3a6943c5b6ffb561f5b35627faf9e3352edc341e23`
- Compact evidence:
  `docs/benchmarks/data/GROOVE_STACKED_ARTICULATION_V18.json`
- Full local 100-record report SHA-256:
  `823143231ae22027a4fe60a0df618fbfa585d087f2c17e41fbd7851fe81838d0`
- Full local multi-kit report SHA-256:
  `c260698e2e27f377b064a6d396c25740a8d16afaa51673df828fc768fb9994e8`

The multi-kit command is identical to the v17 reproduction command except for
the v18 config and output paths. `decode_stacked_probabilities` reads the fixed
`familyConflictMargins` rule from the configuration; it does not inspect
evaluation labels at inference time.

## Remaining bottlenecks

Pedal hi-hat (70.81%), open hi-hat (80.28%), ride bell (84.68%), ride (85.17%),
snare (89.22%), and crash (89.95%) remain the weakest multi-kit classes. The
next material gain needs more rights-cleared natural recordings of these
articulations and a fresh sealed holdout; repeated tuning on the opened suites
would not support a new generalization claim.
