# Sealed original metal benchmark v1

Date completed: 2026-09-01

## Executive Summary

The first untouched full-mix metal benchmark **does not meet the 90% launch
target**. DrumScribe achieved **46.73% class-aware F1 at 50 ms**, **74.36%
onset-only F1 at 50 ms**, and **37.82% exact notation class-and-slot F1** on
the 24-bar original song *Forged in Silence*. The honest release decision is
**blocked for accuracy**; this result must not be marketed as 90% accurate.

Before the sealed run, a training-only event-articulation refiner was evaluated.
It improved known-onset classification for several weak families, but the gain
disappeared when onset discovery was included. That candidate was rejected, and
the previously frozen `groove-stacked-articulation-v16` stack was tested without
changing its checkpoints, thresholds, rules, or tolerance.

## Key findings with visual evidence

| Metric | Result | Target | Decision |
| --- | ---: | ---: | --- |
| Class-aware F1, +/-50 ms | **46.73%** | 90% | Fail |
| Onset-only F1, +/-50 ms | **74.36%** | 90% | Fail |
| Exact notation class-and-slot F1 | **37.82%** | 90% | Fail |
| Supported-class macro F1, +/-50 ms | **25.71%** | 90% | Fail |
| Demucs drum-stem SI-SDR | 13.42 dB | Diagnostic | Strong isolation |
| Estimated first tempo | 176.47 BPM | 180 BPM | 3.53 BPM low |

The source separator was not the primary failure: its isolated stem correlates
0.9780 with the reference and reaches 13.42 dB SI-SDR. The main failure is a
large domain shift between Groove training data and this metal kit. The detector
found many real attacks with high precision, but missed 246 of 655 onsets and
misclassified many detected cymbal, hi-hat, and tom events.

| Class | Reference | Predicted | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Kick | 176 | 192 | 84.38% | 92.05% | **88.04%** |
| Snare | 48 | 67 | 58.21% | 81.25% | 67.83% |
| Cross-stick | 8 | 0 | 0.00% | 0.00% | 0.00% |
| Closed hi-hat | 128 | 8 | 87.50% | 5.47% | 10.29% |
| Open hi-hat | 32 | 71 | 23.94% | 53.12% | 33.01% |
| Pedal hi-hat | 48 | 24 | 16.67% | 8.33% | 11.11% |
| Ride | 64 | 7 | 71.43% | 7.81% | 14.08% |
| Ride bell | 20 | 14 | 100.00% | 70.00% | **82.35%** |
| Crash | 15 | 1 | 0.00% | 0.00% | 0.00% |
| High tom | 13 | 0 | 0.00% | 0.00% | 0.00% |
| Mid tom | 13 | 1 | 100.00% | 7.69% | 14.29% |
| Low tom | 13 | 21 | 19.05% | 30.77% | 23.53% |
| Floor tom | 13 | 39 | 10.26% | 30.77% | 15.38% |
| Tambourine | 64 | 0 | 0.00% | 0.00% | 0.00% |

The per-class comparison is also available as a native chart in the stakeholder
artifact generated with this benchmark. Kick is the only class near the target;
every other class remains below 90% on this song.

## Recommended next steps

1. Treat this song as development data only. Build a rights-cleared metal corpus
   spanning multiple drummers, rooms, kits, productions, tempos, and simultaneous
   hit combinations; do not train only on this one arrangement or sample library.
2. Replace the seven-model validation stack with a deployable multi-label model
   trained on full-mix and separated-stem augmentation. Add explicit cross-stick,
   tambourine, low-tom, detailed hi-hat, and cymbal articulation support.
3. Calibrate timing with a stable tempo/downbeat projection before notation and
   retain Beat This anchors for human timing. The first tempo estimate was 3.53
   BPM low and exact slot matching lagged onset-only matching by 20.18 points.
4. Freeze the next model, then test once on a **second unseen composition and
   unseen recording chain**. Require at least 90% class-aware micro F1, 90%
   supported macro F1, 90% exact notation F1, and no supported class below 85%
   before a limited beta claim.
5. Keep Demucs and Beat This behind the research gate until their model/training
   provenance is approved for the intended commercial deployment.

## Further questions

- Which launch genres and drum kits are in scope for the first paid beta?
- Is the product promise five-class drum transcription or the current 14 detailed
  articulations? The evidence and achievable launch date differ substantially.
- Can the launch dataset and every model dependency be commercially redistributed,
  or must inference remain on founder-controlled infrastructure?
- What minimum song-level sample size and confidence interval will be required for
  marketing accuracy claims?

## Caveats and assumptions

- This is one deterministic, synthetic-but-real-sample song, not a population
  generalization estimate. The composition and guitar/bass performances are
  original; the MuldjordKit FreePats one-shots are CC BY 4.0.
- The 655-event reference covers all 14 DrumScribe classes. Prediction ran once
  before the reference was opened, and no post-test tuning was performed.
- Many earlier model and threshold candidates were selected on the same Groove
  validation split. The old validation score is optimistic and is not substituted
  for this sealed end-to-end result.
- Demucs isolation, the frozen checkpoint stack, Beat This timing, DrumScribe
  quantization, MIDI, MusicXML, PDF export, and rendered-PDF QA were exercised.
- Full raw evidence is under the local ignored benchmark output directory. The
  committed summary is `docs/benchmarks/data/SEALED_ORIGINAL_METAL_V1.json`.
