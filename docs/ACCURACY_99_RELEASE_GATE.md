# DrumScribe 99% accuracy release gate

Date established: 2026-08-30

DrumScribe will not describe a model as 99% accurate from one song, one tolerance, or precision alone. A release passes only when `drumscribe-ml quality-gate` succeeds on a licensed, held-out evaluation set.

## Required evidence

- At least 100 held-out recordings and 10 hours of audio.
- Both isolated-drum and full-mix conditions.
- At least 100 reference events for every canonical instrument.
- At 25 ms: micro precision, recall and F1; macro F1; mean per-song F1; and every per-class precision, recall and F1 must each be at least 0.99.
- Mean matched-onset timing error must be at most 10 ms.
- Beat F1, downbeat F1, class-plus-notation-slot F1, notation-slot F1, tempo accuracy and velocity accuracy must each be at least 0.99.
- Separation correlation must be at least 0.99 and SI-SDR at least 20 dB.
- Export and browser journey pass rates must be 1.0.
- Missing measurements fail the gate. A class with insufficient support fails the gate.

## Current measured position

The existing MDB Beatles-style research benchmark does not pass this gate. The latest full browser run measures 0.940 class precision, 0.610 class recall and 0.740 class F1 at 50 ms. The Beat This timing integration measures 1.000 beat F1 and 1.000 downbeat F1 at 50 ms on that recording and corrects generated tempo from 112.35 BPM to 111.11 BPM. Exact class-plus-slot notation F1 rises from 0.656 to 0.740 and slot-only precision reaches 1.000, but recall remains 0.649.

These figures are research diagnostics, not production generalization evidence. MDB Drums is non-commercial evaluation material and this track was already inspected during DSP development.

The licensed-data pipeline imported 1,076 valid Groove MIDI Dataset recordings while preserving Google's source train/validation/test assignments; 14 audio/annotation pairs with out-of-bounds labels were excluded in full. A controlled three-epoch pilot over a deterministically selected, hashed 100-training/20-validation subset compared the original CRNN (0.597 validation macro F1) with the clean-room spectral MoE (0.674). The 13.0% relative gain advances spectral MoE to scaled experimentation, not production. Thresholds were tuned on validation, all 122 official test recordings remain sealed, and the source corpus contains no low-tom or tambourine labels. Those classes remain explicit blockers rather than being omitted from the release average. See `docs/benchmarks/GROOVE_ARCHITECTURE_PILOT.md`.

A subsequent training-only one-shot pilot added 100 low-tom and 100 tambourine events from disjoint, hashed FreePats sample partitions. The existing 12-class natural-validation macro F1 changed from 0.674 to 0.681, but open hi-hat regressed from 0.691 to 0.551 and the two added classes still had no natural validation support. The augmentation machinery is accepted; its recipe and checkpoint are not production-approved. See `docs/benchmarks/GROOVE_ONE_SHOT_OVERLAY_PILOT.md`.

The scaled local run used all 834 original Groove training records, 100 balanced
one-shot variants and all 120 untouched official validation records. Re-evaluating
the starting checkpoint on that full validation split produced 0.6220 macro F1;
full-corpus training and bounded lower-rate fine-tuning raised the best result to
0.8311 across the 12 naturally supported classes. This is below the requested 0.85
interim target and far below this release gate. A separate reserved synthetic probe
measured 0.8534 across all 14 classes and 0.9937 for low tom plus tambourine, but it
is not natural-performance evidence and is not substituted for the headline score.
At that stage, the official test split remained sealed. See
`docs/benchmarks/GROOVE_FULL_BALANCED_TRAINING.md`.

The subsequent 90% target experiment expanded validation calibration through 0.995,
added deterministic family competition and selected per-class peak suppression on
validation. The same epoch-12 model reached 0.8505 macro F1 across the 12 naturally
supported classes. After the model and calibration were frozen, the official
122-record test split was evaluated once and scored 0.8463; counting unsupported
natural low tom and tambourine as zero gives 0.7254 across all 14 classes. Feature
MixUp, a 300-record rights-cleared articulation overlay, auxiliary articulation
loss, tempered class weights and a bounded 7.29-hour/eight-kit E-GMD fine-tune all
failed to beat the protected validation result. The test split is now opened and
must not be used for future tuning. See
`docs/benchmarks/GROOVE_90_TARGET_ACCURACY.md`.

## Model path

1. Import E-GMD through `drumscribe-ml import-egmd` on dedicated training compute. Its official train, validation and test assignments are preserved, and every kit rendering of one performance stays in the same leakage group.
2. Prepare only the training split with augmentation. Validation and test files remain unchanged.
3. Train the multi-label CRNN over all canonical DrumScribe instruments using class-balanced, onset-tolerant loss and bounded windows.
4. Calibrate each class on validation data, freeze the model and thresholds, and evaluate once on the held-out test split.
5. Use the audited rights-cleared MuldjordKit and FreePats one-shot catalog for training-only class balancing. Preserve disjoint sample partitions, content hashes and attribution in every experiment/model card; do not substitute synthetic probes for the natural held-out release set.
6. Evaluate full mixes after separation and run the browser upload/editor/export/delete journey.
7. Keep production blocked until the gate passes and model, weights, data, attribution and deployment licenses are approved.

## Licensed starting corpus

Google publishes the Groove MIDI Dataset under CC BY 4.0 with 13.6 hours of aligned human-performed drum audio and MIDI. Its supplied test split contains 84.3 minutes and 43,832 hits. E-GMD is also CC BY 4.0 and expands the material to 444 hours across 43 kits; the full archive is 90 GB and should be trained on dedicated compute rather than the API server.
