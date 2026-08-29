# ML evaluation

## Evaluation contract

Each labelled song stores onset seconds, canonical instrument class, duration, split, source kind, licence/attribution metadata, and immutable content hashes. Splits are artist/session-aware where metadata allows, preventing near-duplicate performances from leaking across train and test.

Evaluate two tracks independently:

1. Clean drum stem to transcription.
2. Full mix to separation to transcription.

Every standard report includes 25, 50 and 100 ms onset tolerances. It reports
precision, recall and F1 by class; micro and macro F1; event-count error; false
positives/negatives per minute; matched-onset timing MAE; and per-song results.
The 50 ms view is the primary comparison, not a universal truth. Keep the raw
machine-readable JSON beside the self-contained HTML report.

Source separation is evaluated independently with SI-SDR when a legally usable
ground-truth stem exists and with a controlled 1–5 listening rubric for bleed,
cymbal energy, kick/snare/tom preservation and transient integrity. Coverage is
explicit for studio rock, pop, indie, acoustic rock, dense guitars, bass-heavy,
quiet/loud drums, reverb-heavy, compressed mastering and live material.

## Comparing models

Record provider, code/model/weights hash, parameters, hardware, dependency lock hash, dataset manifest hash, and wall/real-time processing duration. Compare on the same immutable test manifest. Never select a release on aggregate F1 alone: inspect common correction cost, tempo failures, dense fills, and the number of destructive false positives.

The product-quality companion metric is correction burden: events added,
deleted, moved and reassigned; velocity edits; tempo, meter, beat and bar-line
corrections; active correction seconds; corrections/audio minute; and correction
minutes/audio minute. Admin job diagnostics aggregate these counts without
exposing customer media. Provider matrices also report success rate, processing
seconds/audio minute, cost/audio minute and cost/successful transcription.

Customer correction data remains excluded from training unless the owner gave
explicit opt-in consent and the example passed licensing/privacy review.

## Self-hosted lifecycle

`ml/` now implements manifest validation, hash/duration checks, canonical label
preservation, leakage-safe splitting, deterministic bounded audio augmentation,
log-mel feature caching, a multi-label convolutional/bi-GRU onset model with a
velocity head, checkpoint/resume, early stopping, JSONL metric logging,
experiment/Git/dataset/config provenance, model hashing and validation-set
temperature/threshold calibration. This is runnable engineering infrastructure,
not a production-approved checkpoint.

The committed HTML/JSON reports are labelled `synthetic_tooling_only`. They prove
the evaluator works; they do not establish real-song quality. Production remains
blocked until a rights-cleared corpus and real provider credentials are supplied.

## Release gate

No provider is production-selectable unless `MODEL_LICENSING.md` explicitly records commercially allowed code, weights, training data, attribution, and distribution terms. Accuracy, speed, safety, and licensing are independent gates.
