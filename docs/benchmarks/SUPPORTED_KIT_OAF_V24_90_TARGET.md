# Supported-kit OaF v24: 90% target

Date completed: 2026-09-01

## Decision

The frozen `supported-kit-oaf-v24` checkpoint crosses 90% class-balanced F1 for
the narrowly defined MuldjordKit synthetic beta. It scores **90.40% strict
14-class macro F1** on 24 validation performances and **92.11% macro F1** on a
new post-freeze song. After deterministic metal backing and `htdemucs_ft` drum
isolation, that song scores **90.28% macro F1**.

This is not a claim that DrumScribe is 90% accurate on arbitrary commercial
music. The full-mixture test's event-weighted micro F1 is **88.40%**, several
individual articulations remain below 90%, the audio is generated with one
known licensed kit, and the test population is one song. The checkpoint remains
research-only and is not approved for a paid general-audio launch.

## What changed

- Replaced the compact attack-candidate MLP with a clean-room frequency-aware
  2D CNN and bidirectional LSTM operating on complete log-mel sequences.
- Built 120 leakage-separated, full-kit performances with 14-class annotations;
  96 were used for training and 24 for validation.
- Increased temporal capacity from 96 to 192 hidden units, sharpened target
  dilation from five frames to three, and added bounded class loss multipliers
  for the underfit hi-hat, cross-stick, and tom classes.
- Ran one lower-rate continuation from the best v23 checkpoint. The frozen v24
  checkpoint is selected by the unchanged 14-class validation metric.
- Attempted a further separation-domain fine-tune using the already-opened
  `Ashes of the Machine` development stem. It did not improve validation, so
  early stopping retained v24 and the attempted v25 weights were rejected.

## Frozen validation

The validation set contains 24 songs that were never training records. The
metric uses the fixed checkpoint thresholds and duplicate-suppression distances.

| Class | F1 |
| --- | ---: |
| Kick | 98.89% |
| Snare | 94.08% |
| Cross-stick | 78.00% |
| Closed hi-hat | 74.52% |
| Open hi-hat | 85.04% |
| Pedal hi-hat | 82.01% |
| Ride | 87.31% |
| Ride bell | 92.59% |
| Crash | 97.62% |
| High tom | 96.83% |
| Mid tom | 92.27% |
| Low tom | 91.95% |
| Floor tom | 94.52% |
| Tambourine | 100.00% |
| **Strict 14-class macro** | **90.40%** |

## Post-freeze new song

The checkpoint was frozen before song index `10000`, titled `Rivet Storm`, was
rendered. The 12.46-second 169 BPM performance has 227 reference events covering
all 14 classes. No model, threshold, suppression distance, or label was changed
after either test result was opened.

| Condition | Class-balanced macro F1 | Event micro precision | Event micro recall | Event micro F1 |
| --- | ---: | ---: | ---: | ---: |
| Known-kit drum stem | **92.11%** | 88.02% | 93.83% | **90.83%** |
| Metal full mix -> `htdemucs_ft` drum stem | **90.28%** | 87.83% | 88.99% | **88.40%** |

The full-mixture per-class F1 is 91.67% kick, 96.55% snare, 68.57% closed
hi-hat, 66.67% cross-stick, 88.07% pedal hi-hat, 85.71% floor tom, 80.00%
high tom, 93.33% mid/low tom, and 100% for ride, ride bell, open hi-hat, crash,
and tambourine. Crash and ride-bell support is very small, so their single-song
100% scores are not population estimates.

## Why this is not a general 90% launch claim

The strongest recent full-kit frequency-structured result reports 92.0% for
three broad classes but 87.2% for eight classes, illustrating the accuracy cost
of detailed articulation output. Spotify Basic Pitch is an Apache-licensed
pitched-instrument model rather than a 14-class drum detector. A community drum
adaptation of its architecture has useful ideas—frequency features, multiple
drum heads, focal loss, and temporal suppression—but publishes neither a
checkpoint nor a reproducible accuracy result. Dynamic few-shot research
supports kit-specific examples as a way to reduce domain shift, but it does not
remove the need for a natural held-out evaluation population.

References:

- [Frequency-Structured Dilated Conformer full-kit ADT](https://www.mdpi.com/2076-3417/16/13/6746)
- [Spotify Basic Pitch](https://github.com/spotify/basic-pitch)
- [Community Basic-Pitch-style drum adaptation](https://github.com/Teraldan/drums-audio-to-midi)
- [Dynamic few-shot drum transcription](https://publica.fraunhofer.de/entities/publication/ea511ccd-d734-4e99-b98b-e795cba669e1)

## Reproducibility and artifacts

- Frozen checkpoint: `ml/models/supported-kit-oaf-v24.pt`
- Model manifest: `ml/models/supported-kit-oaf-v24.json`
- Checkpoint SHA-256:
  `5615181475f36b3bad0888977333db739b1ddae425579c53797c6a816f8fc027`
- Corpus builder: `scripts/build_supported_kit_corpus.py`
- Prediction/notation exporter: `scripts/export_supported_kit_prediction.py`
- Full-mix renderer: `scripts/render_supported_kit_full_mix.py`
- Separated-stem test preparer: `scripts/prepare_supported_kit_stem_variant.py`
- Local validation evidence: `output/supported-kit-oaf-v24-validation-evidence.json`
- Local post-freeze evidence: `output/supported-kit-oaf-v24-new-song`

## Remaining route to a sellable 90%

1. Replace the one-kit generated population with rights-cleared natural
   recordings spanning drummers, rooms, microphones, mixes, and at least ten kits.
2. Train on the complete E-GMD corpus plus legally cleared detailed-articulation
   data, with kit/drummer leakage groups held out.
3. Add frequency-structured long-context attention or a Conformer and real
   separation-domain training, not a one-song fine-tune.
4. Freeze at least 100 songs and 10 hours, then require both macro and micro F1,
   plus every critical class, to exceed 90 before a general paid-launch claim.
