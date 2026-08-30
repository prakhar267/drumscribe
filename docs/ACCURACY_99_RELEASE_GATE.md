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

The licensed-data pipeline imported 1,076 valid Groove MIDI Dataset recordings while preserving Google's source train/validation/test assignments; 14 audio/annotation pairs with out-of-bounds labels were excluded in full. A three-epoch integration pilot over 100 training and 20 validation recordings reached 0.521 validation macro F1 after per-class threshold calibration. That pilot verifies the training machinery, not model quality. The source corpus contains no low-tom or tambourine labels, so those classes remain explicit blockers rather than being omitted from the release average.

## Model path

1. Import the Groove MIDI Dataset through `drumscribe-ml import-groove`. Its official train, validation and test assignments are preserved.
2. Prepare only the training split with augmentation. Validation and test files remain unchanged.
3. Train the multi-label CRNN over all canonical DrumScribe instruments using class-balanced, onset-tolerant loss and bounded windows.
4. Calibrate each class on validation data, freeze the model and thresholds, and evaluate once on the held-out test split.
5. Add rights-cleared recordings for classes not sufficiently represented in Groove, especially tambourine and four-way tom distinctions.
6. Evaluate full mixes after separation and run the browser upload/editor/export/delete journey.
7. Keep production blocked until the gate passes and model, weights, data, attribution and deployment licenses are approved.

## Licensed starting corpus

Google publishes the Groove MIDI Dataset under CC BY 4.0 with 13.6 hours of aligned human-performed drum audio and MIDI. Its supplied test split contains 84.3 minutes and 43,832 hits. E-GMD is also CC BY 4.0 and expands the material to 444 hours across 43 kits; the full archive is 90 GB and should be trained on dedicated compute rather than the API server.
