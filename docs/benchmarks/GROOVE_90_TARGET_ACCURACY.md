# Groove 90% target accuracy experiment

Date completed: 2026-08-31

> Follow-up: the schema-v2 stacked articulation ensemble reaches 0.9001
> event-weighted micro F1 and 0.8967 supported-class macro F1 on the same natural
> validation set. It therefore crosses 90% only on the event-weighted aggregate,
> still misses the class-balanced target, and has no fresh sealed-test result.
> See `docs/benchmarks/GROOVE_STACKED_ARTICULATION_V16.md`.

Decision: **the model does not meet the 90% target and is not approved for a
production accuracy claim or paid launch.** The strongest validation result is
0.8505 macro F1 across 12 naturally supported classes. The one-time sealed test
result is 0.8463. Both use a two-frame onset tolerance, fixed validation-selected
calibration and exact instrument labels.

## Headline evidence

| Evidence | Recordings | Supported-class macro F1 | Strict 14-class macro F1 | Test-label tuning |
| --- | ---: | ---: | ---: | --- |
| Full natural validation | 120 | **0.8505** | 0.7290 | No |
| Official sealed test | 122 | **0.8463** | 0.7254 | No; thresholds and peak distances were frozen |

The requested 0.90 target is missed by 4.95 points on validation and 5.37 points
on sealed test. Low tom and tambourine have no natural labels in Groove, so they
are counted as zero in the strict 14-class result rather than silently omitted.
The earlier reserved one-shot probe remains synthetic evidence and is not
substituted for natural accuracy.

## Per-class result

| Class | Validation F1 | Sealed-test F1 |
| --- | ---: | ---: |
| Kick | 0.9482 | 0.9403 |
| Snare | 0.8897 | 0.8388 |
| Cross-stick | 0.9505 | 0.9098 |
| Closed hi-hat | 0.7832 | 0.8298 |
| Open hi-hat | 0.7829 | 0.7507 |
| Pedal hi-hat | 0.6952 | 0.5940 |
| Ride | 0.6399 | 0.7380 |
| Ride bell | 0.8358 | 0.8182 |
| Crash | 0.8360 | 0.8687 |
| High tom | 0.9464 | 0.9597 |
| Mid tom | 0.9593 | 0.9585 |
| Floor tom | 0.9386 | 0.9492 |
| Low tom | No natural support | No natural support |
| Tambourine | No natural support | No natural support |

Pedal hi-hat, ride, open hi-hat and ride bell remain the largest exact-class
errors. The sealed-test drop in pedal hi-hat and snare offsets gains in ride,
closed hi-hat and crash.

## What improved

The epoch-12 spectral-MoE model originally measured 0.8311 under the earlier
validation procedure. Expanding the confidence grid through 0.995, applying
validation/test-identical competition within mutually exclusive hi-hat and ride
families, and selecting a bounded per-class minimum peak distance raised the same
model to 0.8505. The absolute improvement is 1.94 points without reading test
labels.

The final checkpoint records all 14 thresholds and peak distances. Sealed test
used `--fixed-checkpoint-thresholds --family-competition`; the evaluator refuses a
fixed evaluation when either calibration map is incomplete. It also labels test
output as `natural_sealed_test` so it cannot be confused with validation or a
synthetic probe.

## Rejected experiments

| Experiment | Natural-validation macro F1 | Decision |
| --- | ---: | --- |
| Arbitrary feature MixUp, first epoch | 0.8116 | Rejected; large regression |
| 300-record rights-cleared articulation overlay | 0.8499 | Rejected overall; hi-hat/ride improved but crash and ride bell regressed |
| Auxiliary articulation loss + tempered positive weights | 0.8451 | Rejected; ride/open recall regressed |
| 7.29-hour, eight-kit E-GMD fine-tune | 0.8246 | Rejected; protected baseline retained |
| Track-level hi-hat/ride mode gate | 0.8506 | Rejected; +0.01 point is not worth a brittle product heuristic |

The E-GMD subset was selected only from the official training split using the
committed SHA-256 selection recipe. It downloaded 800 renders; 784 valid tracks
across 98 performance groups and eight kits passed import. Sixteen malformed pairs
with annotations beyond audio were excluded. The combined prepared set contained
1,918 train, 120 untouched validation and 122 untouched test records. E-GMD is
published under CC BY 4.0 and provides 444 hours across 43 kits; the local subset
was an intentionally bounded experiment, not a replacement for full-corpus
training. See the [official E-GMD dataset page](https://magenta.withgoogle.com/datasets/e-gmd)
and [E-GMD/OaF Drums paper](https://arxiv.org/abs/2004.00188).

## Frozen lineage

- Final validation/test checkpoint SHA-256:
  `b98fe251d7c269fb18dd3474be0109aef1bd6c16b4ee9412308388eae1343625`.
- Combined prepared-manifest SHA-256:
  `2c30f2e251a819e40e868c458d3c2bb190df31cf26ea951167acde439972fea7`.
- Validation metric version: 3.
- Validation recordings: 120 untouched official Groove records.
- Sealed test recordings: 122 untouched official Groove records, evaluated once.
- E-GMD subset recipe: `ml/data/egmd-subset-100x8-v1.json`.

## Commercial-readiness consequence

Do not advertise this as 90% accurate and do not begin selling on this evidence.
The 0.8463 result measures isolated-drum event classification only; it does not
measure the complete full-mix path through separation, beat/downbeat tracking,
notation-slot assignment, velocity, export and browser completion. Production also
remains blocked by the independent 99% release gate and by missing natural low-tom
and tambourine evidence.

The next valid model iteration needs a new development/validation protocol and a
fresh untouched test set. The opened Groove test split must not become a tuning set.
The highest-leverage technical path is full E-GMD training on dedicated compute,
frequency-structured modeling for cymbal articulation, and rights-cleared natural
recordings that include pedal hi-hat, detailed toms and tambourine. Product-level
evaluation must then run on full mixes and report every release-gate metric rather
than a single headline percentage.
