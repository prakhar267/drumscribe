# Groove full-corpus balanced training

Date completed: 2026-08-31

Update: this experiment has been superseded by the validation-safe calibration and
sealed-test work in `docs/benchmarks/GROOVE_90_TARGET_ACCURACY.md`. The newer result
is 0.8505 validation macro F1 and 0.8463 on the one-time sealed test; it still does
not meet the 0.90 target.

Decision: accuracy improved materially, but the natural-validation result does not
pass the requested 0.85 threshold or the production 0.99 release gate.

## Result

The starting one-shot pilot checkpoint scored **0.6220 macro F1** when it was
re-evaluated over all 120 official Groove validation recordings. Training on all
834 original training recordings plus 100 rights-cleared one-shot overlay variants,
then fine-tuning the best checkpoint at lower learning rates, raised the best
natural-validation macro F1 to **0.8311** across the 12 classes with natural Groove
support. This is a gain of **0.2091 absolute** (33.6% relative), but it remains
0.0189 below the requested 0.85 threshold.

Low tom and tambourine have no natural annotations in Groove. Counting those two
unsupported classes as zero gives a strict 14-class natural score of **0.7124**.
They are not silently omitted from the production gate.

| Naturally supported class | Starting F1 | Best F1 | Change |
| --- | ---: | ---: | ---: |
| Kick | 0.725 | 0.945 | +0.220 |
| Snare | 0.835 | 0.889 | +0.054 |
| Cross-stick | 0.890 | 0.948 | +0.058 |
| Closed hi-hat | 0.526 | 0.771 | +0.244 |
| Open hi-hat | 0.466 | 0.753 | +0.287 |
| Pedal hi-hat | 0.398 | 0.680 | +0.282 |
| Ride | 0.281 | 0.622 | +0.341 |
| Ride bell | 0.407 | 0.799 | +0.392 |
| Crash | 0.641 | 0.778 | +0.137 |
| High tom | 0.865 | 0.920 | +0.055 |
| Mid tom | 0.659 | 0.943 | +0.284 |
| Floor tom | 0.771 | 0.926 | +0.155 |

Ride and pedal hi-hat remain the weakest naturally measured classes. The official
122-record Groove test split was not used for training, threshold selection, model
selection or this report; it remains sealed for a future frozen-model evaluation.

## Training lineage

- Prepared-data SHA-256:
  `69c9fb330b3368b13310eb28e21d5d4f94806eb852b7843c59e742b1f8dff3fc`.
- Records: 934 train, 120 validation and 122 sealed test. The training set contains
  834 natural records and 100 overlay variants.
- Overlay support: 100 low-tom and 100 tambourine events from training-only sample
  partitions. Validation and test source records remained unchanged.
- Best natural checkpoint: epoch 12 after resuming the epoch-8 full-corpus model at
  a 0.0001 learning rate.
- Best checkpoint SHA-256:
  `221d9af4fee4579fee1291b0c0600d1039cef5570e9de1b9489480c35fefa694`.
- Main trajectory: 0.6656 at epoch 3, 0.8011 at epoch 8 and 0.8311 at epoch 12.
  Later 0.0001 and 0.00005 attempts regressed, so best-checkpoint selection retained
  epoch 12.

Resume logic now hashes the prepared manifest and resets inherited validation state
when the data changes. Training records receive a deterministic epoch-specific
shuffle. Plateau learning-rate decay, explicit resume-rate overrides and
evaluation-only manifest rejection are recorded in experiment metadata.

## Reserved one-shot probe

A separate evaluation-only probe overlays one low-tom and one tambourine event onto
each of the 120 source validation recordings using only the reserved validation
sample partition. Its prepared-manifest SHA-256 is
`95ff232ae698aa22d650c242de5ed7d01812d65441551f684b365cf28f5e6c43`.

| Probe metric | Starting checkpoint | Improved checkpoint |
| --- | ---: | ---: |
| Low-tom F1 | 0.9874 | 0.9916 |
| Tambourine F1 | 1.0000 | 0.9959 |
| Low-tom/tambourine macro F1 | 0.9937 | 0.9937 |
| All 14 classes on probe recordings | 0.6750 | 0.8534 |

The 0.8534 probe result is **not** the natural accuracy headline. The two added
classes are isolated synthetic one-shots, so this probe establishes pipeline and
sample-partition behavior, not performance on natural musical passages.

## Next accuracy gate

Do not production-promote this checkpoint. The next evidence-producing step is to
train on E-GMD or an equivalent rights-cleared corpus with natural low-tom,
tambourine, ride and hi-hat articulation coverage on dedicated compute. Freeze the
model and thresholds after validation, then evaluate the sealed test split once.
Product-level accuracy must additionally include full-mix separation, timing,
notation-slot and export measurements defined in the 99% release gate.
