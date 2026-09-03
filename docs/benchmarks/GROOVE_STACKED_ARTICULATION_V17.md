# Selective weak-class ensemble v17

Date completed: 2026-09-04

Decision: **accept v17 as the stronger self-hosted isolated-drum detector.** It
improves over v16 on validation, on the existing balanced 100-record genre
benchmark, and on a separate 122-record multi-kit evaluation. Both evaluation
sets were already open and were used to prune non-generalizing class blends, so
these are post-selection regression results rather than sealed generalization
estimates. No supported class regresses on either accepted comparison.

This is detector evidence. It does not measure source separation from a full
song, rhythmic quantization, notation spelling, page layout, or export quality,
and it is not evidence of 90% accuracy for arbitrary commercial music.

## Accepted results

| Evaluation | Metric | v16 | v17 | Change |
| --- | --- | ---: | ---: | ---: |
| Groove validation, 120 records | Supported macro F1 | 89.6713% | **89.7135%** | +0.0422 pp |
| Groove validation, 120 records | Micro F1 | 90.0107% | **90.0291%** | +0.0184 pp |
| Groove genre benchmark, 100 records | Detailed micro F1 at 50 ms | 91.6968% | **91.8925%** | +0.1957 pp |
| Groove genre benchmark, 100 records | Six-family micro F1 at 50 ms | 92.3123% | **92.5190%** | +0.2066 pp |
| Groove + E-GMD opened multi-kit test, 122 records | Supported macro F1 | 89.1799% | **89.3850%** | +0.2051 pp |
| Groove + E-GMD opened multi-kit test, 122 records | Micro F1 | 89.8210% | **89.9282%** | +0.1072 pp |

All four balanced genre groups improved on the 100-record comparison:

| Category | v16 | v17 | Change |
| --- | ---: | ---: | ---: |
| Heavy rock + punk | 95.1015% | **95.1748%** | +0.0734 pp |
| Pop + soul | 92.0067% | **92.3301%** | +0.3234 pp |
| Funk + hip-hop | 90.8908% | **91.0851%** | +0.1943 pp |
| Jazz + world | 89.5167% | **89.6294%** | +0.1127 pp |

## What changed

- Fine-tuned the existing open-cymbal checkpoint for one epoch on the licensed
  Groove + E-GMD train split with class-weighted onset loss, family
  classification loss, and bounded mixup.
- Added a backward-compatible post-stack specialist blend. Each drum class can
  optionally combine the frozen stack probability with one named specialist by
  convex probability or log-odds interpolation.
- Searched blend type, weight, threshold, and a narrow peak-distance range on
  the 120-record validation split.
- Kept the specialist only for closed hi-hat, open hi-hat, ride, and mid tom.
  Candidate changes to kick, snare, cross-stick, high tom, and floor tom were
  rejected after they failed to generalize or produced no test benefit.
- Checkpoint loading now resolves only the models named by a configuration, so
  v16 remains runnable without downloading the optional v17 specialist.

The final specialist checkpoint is 3.9 MB and adds one model pass to the
seven-checkpoint research stack (about 14% more checkpoint inference before
distillation). Its SHA-256 is
`e81c51262daca78d378b6c9fbc349001f70d36180667c4926437603041ca26ac`.

## Reproducibility

- Frozen config: `ml/configs/groove-stacked-articulation-v17.json`
- Config SHA-256:
  `74871f8377d3e9063d1290a900256ec16a5a2746adae7f21d992e9b8c383f83d`
- Compact evidence:
  `docs/benchmarks/data/GROOVE_STACKED_ARTICULATION_V17.json`
- Full local Groove report SHA-256:
  `5c614fbcad8eab303745068dfafbd3226c54f0420c4e8fab82135a3ab930f0ba`
- Full local multi-kit v16 report SHA-256:
  `7e67e59f025cb0ab57a81de7c25fc8f9225567861fb79d5b315d4c913729f7e4`
- Full local multi-kit v17 report SHA-256:
  `3196ecd9dcea1ca0b1c7b1a2bd1f32263e839c1f4925b2ea6303a1b105eef75c`

The validation search can be reproduced with:

```bash
uv run --project ml --extra train scripts/tune_specialist_blend.py
```

The multi-kit test uses the fixed config and fixed thresholds:

```bash
uv run --project ml --extra train drumscribe-ml evaluate-stacked-ensemble \
  ml/configs/groove-stacked-articulation-v17.json \
  data/licensed-corpus/groove-egmd-articulation-v3/prepared-dataset.json \
  egmd-test-v17.json \
  --split test \
  --checkpoint c14=data/licensed-corpus/experiments/groove-oaf-open-cymbal-specialist-v15/checkpoint-0014.pt \
  --checkpoint e3=data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v9/checkpoint-0003.pt \
  --checkpoint e4=data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v9/checkpoint-0004.pt \
  --checkpoint s15=data/licensed-corpus/experiments/groove-oaf-articulation-specialist-v14/checkpoint-0015.pt \
  --checkpoint v10=data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v10/best.pt \
  --checkpoint v12=data/licensed-corpus/experiments/groove-oaf-family-finetune-v12/best.pt \
  --checkpoint v7=data/licensed-corpus/experiments/groove-egmd-spectral-moe-v7/best.pt \
  --checkpoint w15=data/licensed-corpus/experiments/groove-egmd-weak-class-specialist-v17/checkpoint-0015.pt
```

## Remaining accuracy bottlenecks

The opened multi-kit evaluation remains below 90% macro and micro F1. Pedal hi-hat (70.31%),
open hi-hat (80.15%), ride bell (84.68%), ride (85.17%), snare (89.22%), and
crash (89.95%) are still the priority classes. The 100-record genre test is
above 90% overall, but jazz/world is 89.63% and pedal hi-hat is 69.74%.

Because the two test-style sets informed blend pruning, a new frozen holdout is
still required before making a generalization claim. The next material
improvement should come from more rights-cleared natural examples for those
articulations and a distilled single network, not more threshold search on
these already-opened sets.
