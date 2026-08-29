# ML evaluation

## Evaluation contract

Each labelled song stores onset seconds, canonical instrument class, duration, split, source kind, licence/attribution metadata, and immutable content hashes. Splits are artist/session-aware where metadata allows, preventing near-duplicate performances from leaking across train and test.

Evaluate two tracks independently:

1. Clean drum stem to transcription.
2. Full mix to separation to transcription.

At a configurable onset tolerance (50 ms is a useful reporting default, not a universal truth), report precision, recall, F1 by class; micro and macro F1; event-count error; false positives/negatives per minute; matched-onset timing MAE; and per-song results. Keep the raw machine-readable JSON beside the self-contained HTML report.

## Comparing models

Record provider, code/model/weights hash, parameters, hardware, dependency lock hash, dataset manifest hash, and wall/real-time processing duration. Compare on the same immutable test manifest. Never select a release on aggregate F1 alone: inspect common correction cost, tempo failures, dense fills, and the number of destructive false positives.

The product-quality companion metrics are processing success/time, time to first playback, editor-open and export rate, corrected/deleted/added event ratios, practice usage, and estimated manual work saved. Customer correction data remains excluded unless the owner gave explicit opt-in consent and the example passed licensing/privacy review.

## Release gate

No provider is production-selectable unless `MODEL_LICENSING.md` explicitly records commercially allowed code, weights, training data, attribution, and distribution terms. Accuracy, speed, safety, and licensing are independent gates.

