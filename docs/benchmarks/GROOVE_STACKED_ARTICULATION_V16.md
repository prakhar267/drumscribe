# Stacked articulation ensemble v16

Date completed: 2026-09-01

Decision: **overall event-weighted validation F1 crossed 90% at 0.9001, but the
supported-class macro F1 is 0.8967 and therefore still misses the 0.90
class-balanced target by 0.33 points.** This is isolated-drum validation evidence,
not a fresh sealed-test estimate or an end-to-end mixture-to-notation score. Do
not advertise the product as “90% accurate in every aspect” or treat this result
as approval for a paid production launch.

## Frozen result

| Metric | Result | Population |
| --- | ---: | --- |
| Event-weighted micro F1 | **0.9001066477** | 34,182 TP, 2,166 FP, 5,421 FN |
| Supported-class macro F1 | **0.8967130053** | 12 naturally supported Groove classes |
| Strict 14-class macro F1 | 0.7686111474 | Low tom and tambourine counted as zero |
| Validation recordings | 120 | Official Groove validation split |
| Onset tolerance | ±2 frames | Fixed for every class |

The micro result weights common events more heavily; the macro result gives every
supported class equal weight. The latter remains the interim accuracy gate because
it prevents strong kick/snare performance from hiding weak pedal/open hi-hat and
ride performance.

## Per-class validation F1

| Class | F1 |
| --- | ---: |
| Kick | 0.953384 |
| Snare | 0.922841 |
| Cross-stick | 0.965235 |
| Closed hi-hat | 0.880787 |
| Open hi-hat | 0.814494 |
| Pedal hi-hat | 0.756839 |
| Ride | 0.823813 |
| Ride bell | 0.882227 |
| Crash | 0.857835 |
| High tom | 0.964690 |
| Mid tom | 0.976898 |
| Floor tom | 0.961512 |
| Low tom | No natural validation support |
| Tambourine | No natural validation support |

## What changed

- Added canonical per-class loss multipliers and trained two bounded specialists:
  one for pedal/crash recall and one for open-hi-hat/cymbal recall.
- Added a schema-v2 stacked evaluator with named, hash-pinned checkpoints,
  arbitrary convex or linear fusion, log-odds fusion, maximum/noisy-OR rules,
  fixed odd-length temporal kernels, and fixed peak decoding.
- Combined seven checkpoints only where validation showed complementary errors.
  Strong classes retain their earlier protected rules.
- Added a CLI that requires every named checkpoint from the config and rejects
  missing, extra, or hash-mismatched weights. It never fits thresholds on the
  requested evaluation split.

The stack raises supported macro F1 from the prior frozen 0.884501 result to
0.896713, an absolute gain of 1.22 points. Event-weighted micro F1 reaches 0.900107.

## Reproducibility

- Frozen config: `ml/configs/groove-stacked-articulation-v16.json`.
- Durable result summary:
  `docs/benchmarks/data/GROOVE_STACKED_ARTICULATION_V16.json`.
- Prepared-manifest SHA-256:
  `9ef041078b1ffd41965b9fabf1933606b5bc86185f28c5f3c57f1348afaf1426`.
- Exact checkpoint SHA-256 values are pinned in the config and repeated in the
  result summary.
- Test status: `not_evaluated_no_fresh_sealed_set`.

Reproduction command:

```bash
uv run --project ml --extra train drumscribe-ml evaluate-stacked-ensemble \
  ml/configs/groove-stacked-articulation-v16.json \
  data/licensed-corpus/groove-full-articulation-overlay-v2/prepared-dataset.json \
  stacked-validation.json \
  --checkpoint c14=data/licensed-corpus/experiments/groove-oaf-open-cymbal-specialist-v15/checkpoint-0014.pt \
  --checkpoint e3=data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v9/checkpoint-0003.pt \
  --checkpoint e4=data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v9/checkpoint-0004.pt \
  --checkpoint s15=data/licensed-corpus/experiments/groove-oaf-articulation-specialist-v14/checkpoint-0015.pt \
  --checkpoint v10=data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v10/best.pt \
  --checkpoint v12=data/licensed-corpus/experiments/groove-oaf-family-finetune-v12/best.pt \
  --checkpoint v7=data/licensed-corpus/experiments/groove-egmd-spectral-moe-v7/best.pt \
  --split validation
```

The command reproduced every class score, supported macro F1, strict macro F1,
and micro F1 exactly.

## Validation assessment

Assessment: **share with caveats** for engineering progress; **not sufficient for
a launch accuracy claim**.

The headline calculations were independently recomputed from the saved counts,
the 120 records are 120 unique official validation track IDs, the prepared file
hash matches, and low tom/tambourine exclusions are explicit. However, many model,
blend, temporal-kernel, and threshold candidates were compared on this same
validation split. That repeated selection makes 0.9001/0.8967 optimistic as an
estimate of generalization. The old Groove test split was already opened and was
not reused.

The next valid gate is a new rights-cleared, untouched test set with natural
support for all 14 classes, followed by the complete full-mix separation, timing,
notation, export, and browser journey. The seven-checkpoint stack is also a
validation reference implementation, not yet wired into the production worker;
latency/cost should be reduced through distillation before deployment.
