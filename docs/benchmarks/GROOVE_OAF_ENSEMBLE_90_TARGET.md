# Frequency-aware Groove ensemble: 90% target follow-up

Date completed: 2026-08-31

Decision: **the strongest reproducible natural-validation result is 0.8845 macro
F1, so DrumScribe still does not meet the 0.90 target.** This is a 3.40-point
absolute improvement over the prior 0.8505 validation baseline and leaves a
1.55-point gap. The opened Groove test split was not used again. No fresh sealed
test result exists, so this model is not approved for a 90% marketing claim or a
paid production launch.

## Comparable headline evidence

| Model or decoder | Validation recordings | Supported classes | Macro F1 | Gap to 0.90 |
| --- | ---: | ---: | ---: | ---: |
| Protected spectral-MoE baseline | 120 | 12 | 0.8505 | -0.0495 |
| Frequency-aware OaF-style checkpoint | 120 | 12 | 0.8667 | -0.0333 |
| Frozen OaF + spectral ensemble | 120 | 12 | **0.8845** | **-0.0155** |

All values use exact canonical instrument labels, a two-frame onset tolerance,
the official untouched Groove validation recordings, and validation-selected
thresholds plus bounded peak suppression. Low tom and tambourine have no natural
Groove support. Counting them as zero gives the ensemble a strict 14-class macro
F1 of 0.7581.

## Per-class ensemble result

| Class | Validation F1 | Decoder |
| --- | ---: | --- |
| Kick | 0.9503 | Noisy OR |
| Snare | 0.9225 | OaF |
| Cross-stick | 0.9626 | 70% spectral / 30% OaF |
| Closed hi-hat | 0.8673 | Noisy OR |
| Open hi-hat | 0.8063 | 10% spectral / 90% OaF |
| Pedal hi-hat | 0.7338 | 30% spectral / 70% OaF |
| Ride | 0.7855 | OaF |
| Ride bell | 0.8522 | Noisy OR |
| Crash | 0.8363 | 95% spectral / 5% OaF |
| High tom | 0.9628 | 30% spectral / 70% OaF |
| Mid tom | 0.9769 | Maximum probability |
| Floor tom | 0.9573 | 60% spectral / 40% OaF |
| Low tom | No natural support | Not included in supported macro F1 |
| Tambourine | No natural support | Not included in supported macro F1 |

Pedal hi-hat, ride, and open hi-hat remain the limiting classes. Their errors are
large enough that aggregate optimization alone is unlikely to close the remaining
gap honestly; the next data/model iteration needs natural articulation examples.

## Architecture and calibration

The new checkpoint uses a clean-room PyTorch implementation of the public
[Onsets-and-Frames Drums](https://magenta.withgoogle.com/oaf-drums) architectural
pattern: a frequency-aware 2D convolutional front end, frequency pooling and
projection, followed by a bidirectional LSTM and separate onset/velocity heads.
DrumScribe does not load or redistribute [Magenta code or
weights](https://github.com/magenta/magenta/tree/main/magenta/models/onsets_frames_transcription).
The implementation is trained on the rights-cleared DrumScribe corpus.

The single OaF-style checkpoint peaked at epoch 10 with 0.866744 macro F1. A
low-rate E-GMD continuation reached only 0.863550 and was rejected. The frozen
ensemble then selected one validation-only decoder per class from bounded convex,
maximum and noisy-OR candidates. Its configuration pins both checkpoint hashes,
all 14 class rules, thresholds, and minimum peak distances. The productionized
evaluator refuses checkpoint hash mismatches and does not tune on its evaluation
split.

Calibration runtime was also improved without changing the metric: local maxima
are cached across threshold candidates, and peak suppression now uses a bounded
blocked-frame mask rather than comparing every candidate with every prior peak.

## External model checks

- The official [YourMT3 repository](https://github.com/mimbres/YourMT3) was
  evaluated locally as a research diagnostic.
  On a deterministic 62-record validation slice it scored 0.3729 macro F1 versus
  DrumScribe's 0.8287 on the same slice, so it was rejected as the next backend.
  This diagnostic is not directly comparable to the full 120-record headline.
- [ADTOF](https://github.com/MZehren/ADTOF) was evaluated locally only.
  Generic-family F1 on the full validation set
  ranged from 0.6842 for cymbals to 0.8329 for toms, below the current exact-class
  system. Its non-commercial model terms also exclude it from the launch path; no
  ADTOF code or weights are shipped.
- [OaF Drums/E-GMD](https://magenta.withgoogle.com/oaf-drums) remains the viable
  architecture-and-data reference because the public code is Apache-licensed and
  E-GMD is CC BY 4.0. The current bounded E-GMD continuation did not improve
  validation, so the protected OaF checkpoint was retained.

## Frozen reproducibility lineage

- Ensemble config: `ml/configs/groove-oaf-v10-spectral-v7-ensemble-v1.json`.
- OaF checkpoint SHA-256:
  `23a9057d2df6bccde14bce72c280f0bbdbe23236ed4c6e785f2e3496f198ff00`.
- Spectral checkpoint SHA-256:
  `b98fe251d7c269fb18dd3474be0109aef1bd6c16b4ee9412308388eae1343625`.
- Prepared validation manifest SHA-256:
  `9ef041078b1ffd41965b9fabf1933606b5bc86185f28c5f3c57f1348afaf1426`.
- Validation metric version: 3.
- Validation recordings: 120 untouched official Groove records.
- Supported classes: 12; low tom and tambourine have zero natural support.
- Test status: `not_evaluated_no_fresh_sealed_set`.

Reproduction command:

```bash
uv run --project ml --extra train drumscribe-ml evaluate-ensemble \
  ml/configs/groove-oaf-v10-spectral-v7-ensemble-v1.json \
  data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v10/best.pt \
  data/licensed-corpus/experiments/groove-egmd-spectral-moe-v7/best.pt \
  data/licensed-corpus/groove-full-articulation-overlay-v2/prepared-dataset.json \
  ensemble-validation.json --split validation
```

The command reproduced 0.8845011521832195 exactly over all 120 validation
recordings with fixed calibration.

## Release consequence and next step

Do not advertise “90% accurate” yet. The current number measures isolated-drum
event detection, not the full mixture-to-notation journey, and it is validation
evidence rather than a fresh sealed-test estimate.

The shortest honest path to 0.90 is to freeze this ensemble as the comparison
baseline, collect or license a new development corpus rich in pedal/open hi-hat
and ride articulations, train the frequency-aware model on that material, and
reserve a new rights-cleared test set before experimentation begins. A candidate
must first exceed 0.90 on development validation, then confirm the gain once on
the new sealed set and pass the end-to-end product gates.
