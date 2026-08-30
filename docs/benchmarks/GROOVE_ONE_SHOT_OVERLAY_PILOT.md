# Groove one-shot overlay pilot

Date: 2026-08-30

Decision: accept the augmentation pipeline; do not promote this recipe or checkpoint

## Purpose

This experiment verifies that rights-cleared low-tom and tambourine sounds can be
added to training data without contaminating source validation or test records. It
also checks whether the added training variants cause a broad regression across the
12 Groove classes that have natural validation labels.

It does not establish low-tom or tambourine accuracy. Groove has no natural labels
for those classes, and synthetic training examples cannot replace held-out,
rights-cleared performance evidence.

## Data controls

- Source pilot: the same deterministic 100-train/20-validation Groove subset used
  in the architecture comparison.
- Source prepared SHA-256: `769531a9e9e1291d671020d2957385fcdea961151ba34bb15b9abc718abe92c9`.
- Overlay prepared SHA-256: `be50080dbaee9bf293e57d16e785e0ab8f054de2ae3cfa7968ba5b65437e8cd1`.
- One-shot corpus SHA-256: `427e674e82c9f36fc146a00bae29720a1d05632f425f33d03bac6d0731930ccd`.
- MuldjordKit low tom: 11 training sounds, 2 validation sounds and 2 test sounds.
- FreePats tambourine: 20 training sounds, 2 validation sounds and 2 test sounds.
- Generated support: 100 low-tom and 100 tambourine events across 100 new training variants.
- Validation: all 20 source records remained unchanged.
- Official test: absent from both pilot manifests and still sealed.

Each overlay records its class, onset, gain, velocity, source ID, relative sample
path, sample hash, sample partition and corpus hash. Experiment metadata copies the
license attribution and all partition hashes.

## Smoke result

Both runs use the same spectral-MoE architecture and natural validation records.
The overlay run has twice as many training records, so this is a safety smoke test,
not a strictly isolated augmentation-effect estimate.

| Metric | No overlay | With overlay | Change |
| --- | ---: | ---: | ---: |
| Best natural-validation macro F1 | 0.674 | 0.681 | +0.0066 (+0.98%) |
| Training records | 100 | 200 | +100 |
| Naturally evaluable classes | 12 | 12 | unchanged |
| Low-tom synthetic training events | 0 | 100 | +100 |
| Tambourine synthetic training events | 0 | 100 | +100 |

Best-epoch natural-validation per-class F1:

| Class | No overlay | With overlay | Change |
| --- | ---: | ---: | ---: |
| Kick | 0.722 | 0.746 | +0.024 |
| Snare | 0.856 | 0.853 | -0.003 |
| Cross-stick | 0.951 | 0.964 | +0.013 |
| Closed hi-hat | 0.496 | 0.497 | +0.001 |
| Open hi-hat | 0.691 | 0.551 | -0.140 |
| Pedal hi-hat | 0.368 | 0.367 | -0.001 |
| Ride | 0.322 | 0.328 | +0.006 |
| Ride bell | 0.479 | 0.574 | +0.095 |
| Crash | 0.754 | 0.775 | +0.021 |
| High tom | 0.886 | 0.894 | +0.008 |
| Mid tom | 0.750 | 0.776 | +0.026 |
| Floor tom | 0.819 | 0.848 | +0.029 |
| Low tom | no natural support | no natural support | unmeasured |
| Tambourine | no natural support | no natural support | unmeasured |

The overlay checkpoint SHA-256 is
`06280c340e264336bb524891bfd32766191ffc7fd806accab099b80fa8f11b5e`.

## Decision and next gate

Keep the pipeline because it is deterministic, license-gated, partitioned,
training-only and fully traceable. Do not promote the recipe or checkpoint because
open hi-hat regressed materially and the added classes remain unmeasured on natural
performances.

Before scaled training, add an auxiliary synthetic probe using only the reserved
validation one-shots, then tune class-balanced sampling without using the reserved
test sounds. The production-quality run still requires E-GMD on dedicated training
compute: the archive is approximately 90 GB while this workstation currently has
about 27 GB free. Cloudflare Workers and Neon are application infrastructure, not
GPU training capacity.
