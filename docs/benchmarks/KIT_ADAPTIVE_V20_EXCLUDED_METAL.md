# Kit-adaptive v20: excluded-performance metal benchmark

Date completed: 2026-09-01

## Decision

`kit-adaptive-corpus-v20` does **not** meet the 90% launch target and remains a
research backend. Its first run on the second excluded performance achieved
**65.40% class-aware F1 at 50 ms**, **76.20% onset-only F1**, **61.28%
supported-class macro F1**, and **51.97% exact notation class-and-slot F1**.
The result is below the release threshold and must not be advertised as 90%.

## What changed

- Replaced single-label attack decoding with multi-label output so kick, snare,
  cymbal, and hi-hat layers can share one onset.
- Increased transient discovery to 20 ms spacing and the 10th-percentile
  spectral-flux threshold, favoring recall before classification.
- Trained a clean-room NumPy-serving/PyTorch-training MLP on 1,609 licensed
  Groove/E-GMD training records (15.6 hours in the prepared corpus), plus two
  already-unsealed metal development domains.
- Added per-class event-level non-maximum suppression. Thresholds and suppression
  distances were selected on 120 validation recordings plus development data,
  then frozen before the excluded test.
- Kept serving independent of PyTorch. The checkpoint is a hash-pinned NPZ and
  the external runner emits the existing DrumScribe JSON contract.

The corrected event-level calibration reached 81.49% micro F1. On the first
unsealed metal development performance, v20 reached 88.86% F1 with 97.62%
precision. That development number was not substituted for a test result.

## Frozen excluded test

The excluded group was `drummer1/session1/101`. All nine versions of that
performance were removed before training. A fixed 35-second crop was mixed with
new deterministic metal guitar and bass, separated with `htdemucs_ft`, predicted
once, and only then compared with the licensed annotation. No post-test threshold
or model tuning was performed.

| Metric | Result | Target | Decision |
| --- | ---: | ---: | --- |
| Class-aware F1, +/-50 ms | **65.40%** | 90% | Fail |
| Class-aware precision, +/-50 ms | 73.93% | 90% | Fail |
| Class-aware recall, +/-50 ms | 58.64% | 90% | Fail |
| Onset-only F1, +/-50 ms | **76.20%** | 90% | Fail |
| Exact notation class-and-slot F1 | **51.97%** | 90% | Fail |
| Supported-class macro F1 | **61.28%** | 90% | Fail |
| Drum-stem SI-SDR | 11.65 dB | Diagnostic | Usable, not release-grade |
| Drum-stem correlation | 0.9675 | Diagnostic | Strong |

The test had 382 reference events and 303 predictions. The largest errors were
snare recall (47.13%), closed-hi-hat recall (47.27%), and pedal-hi-hat precision
(16.67%). Kick reached 88.57% F1, cross-stick and high tom reached 100% on their
limited support, but no single-song per-class result is a population claim.

## Open-model and commercial-player findings

- Spotify Basic Pitch is pitched-note audio-to-MIDI, optimized for one pitched
  instrument at a time. It has no drum-articulation output head and cannot replace
  the detector.
- Klangio Drum2Notes exposes a drum-specific product, user-selected kit/cymbal
  choices, and editable PDF/MIDI/MusicXML output, but does not publish an
  independently reproducible accuracy score or its model.
- ADT-STR's strongest applicable idea is diverse one-shot curation followed by
  sequence decoding. Its repository did not provide a deployable licensed
  checkpoint at review time.
- Noise-to-Notes reports that adding pretrained music representations materially
  improves cross-domain results, but no public implementation/checkpoint was found
  and the official MERT-v1-95M checkpoint is non-commercial.
- Separate-and-Detect and DrumSep are useful research baselines, but neither
  provides evidence of 90% performance across DrumScribe's 14 detailed classes
  with a production-cleared checkpoint.

## Required route to 90%

1. Train a temporal convolution/Transformer model over the full 444-hour E-GMD
   corpus, not the local 7.29-hour subset, with held-out kit and drummer splits.
2. Add commercially cleared metal/rock separated-stem augmentation and diverse
   one-shot renderings for snares, hi-hat articulations, cymbals, toms, and
   simultaneous combinations.
3. Add a long-context sequence decoder and kit-conditioning controls. These are
   the transferable ideas from ADT-STR and commercial drum-specific workflows.
4. Keep at least 100 recordings and 10 hours completely untouched, then require
   both event-weighted and class-balanced F1 to pass 90% before any paid-launch
   claim. A single selected song cannot certify the product.

## Artifacts

- Frozen checkpoint: `ml/models/kit-adaptive-corpus-v20.npz`
- Checkpoint manifest: `ml/models/kit-adaptive-corpus-v20.json`
- Reproducible trainer: `scripts/train_corpus_kit_adapter.py`
- Three-phase benchmark: `scripts/run_excluded_metal_benchmark.py`
- Local full evidence: `output/metal-excluded-benchmark-v20-2026-09-01`
