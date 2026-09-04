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

A clean-room frequency-aware 2D CNN plus bidirectional LSTM subsequently reached
0.8667 supported-class macro F1 on the same 120 natural validation recordings. A
frozen, hash-pinned per-class ensemble with the protected spectral-MoE checkpoint
raised validation to 0.8845. This is 3.40 points above the prior 0.8505 validation
baseline but still 1.55 points below the interim 0.90 target. No fresh sealed test
set exists, so the opened Groove test split was not rerun and the ensemble is not
approved for a production accuracy claim or paid launch. Low tom and tambourine
still lack natural validation support. See
`docs/benchmarks/GROOVE_OAF_ENSEMBLE_90_TARGET.md`.

A subsequent hash-pinned seven-checkpoint stack adds articulation specialists,
log-odds fusion and fixed temporal kernels. It reproduces 0.9001 event-weighted
micro F1 and 0.8967 supported-class macro F1 on the same 120 validation records.
The micro aggregate has crossed 90%, but the class-balanced target has not; low
tom and tambourine remain unsupported, repeated validation selection makes the
estimate optimistic, and no fresh sealed test exists. This is not a “90% in every
aspect” claim and does not change the 99% production gate. See
`docs/benchmarks/GROOVE_STACKED_ARTICULATION_V16.md`.

The clean-room `kit-adaptive-corpus-v20` experiment then added dense 20 ms
candidate discovery, multi-label simultaneous-hit decoding, diverse licensed
Groove/E-GMD training, separation-domain adaptation, and validation-calibrated
per-class duplicate suppression. It reached 81.49% event-level micro F1 at 50 ms
on the development calibration population and 88.86% on the first now-unsealed
metal development song. On a second excluded performance mixed with newly
generated metal backing, its single frozen end-to-end run scored 65.40%
class-aware F1, 76.20% onset-only F1, and 51.97% exact notation F1. This confirms
that the remaining blocker is cross-performance snare/hi-hat generalization, not
only duplicate decoding. See
`docs/benchmarks/KIT_ADAPTIVE_V20_EXCLUDED_METAL.md`.

The subsequent one-kit frequency-aware experiment trains a clean-room 2D CNN
plus bidirectional LSTM on 96 generated MuldjordKit performances. Its frozen v24
checkpoint reaches 90.40% strict 14-class macro F1 on 24 synthetic validation
songs. A new post-freeze song reaches 92.11% macro and 90.83% micro F1 on the
clean drum stem; after metal backing and `htdemucs_ft` isolation it reaches
90.28% macro but only 88.40% micro F1. This passes a narrow supported-kit macro
target, not the product release gate: the population is synthetic and single-kit,
the full-pipeline micro metric is below 90%, and closed hi-hat/cross-stick remain
weak. See `docs/benchmarks/SUPPORTED_KIT_OAF_V24_90_TARGET.md`.

The confidence-gated rhythm-completion hybrid subsequently reached 97.35%
six-family micro F1 and 96.80% detailed-class micro F1 at 20 ms on a new
post-freeze 12-genre Holdout B. Every per-genre micro score was above 90%, and
the same files scored 65.54% with Drum2Notes. However, the detailed-class macro
F1 is 84.77%; crash, cross-stick, individual toms and open hi-hat remain below
90%. The suite is deterministic, synthetic and single-kit, so it is a lab
regression gate rather than a broad commercial-song estimate. See
`docs/benchmarks/CROSS_GENRE_HOLDOUT_B_V2.md`.

The 2026-09-03 real-performance research pass evaluated eleven manually
annotated MDB Drums MIREX test performances without test-label calibration.
The best end-to-end full-mixture path (`htdemucs_ft` then ADTOF) reached 82.98%
six-family micro F1 at 50 ms; ideal drum stems reached 85.01%. The same round
reproduced 96.43% on the opened synthetic metal development suite and 97.33%
on the opened quiet-song probe, but neither can support a general-song claim.
The company owner subsequently recorded separate DrumScribe commercial rights
for ADTOF and the pinned Demucs artifacts under
`OWNER-ATTESTATION-2026-09-05`. This resolves the provider-rights gate for the
selected self-hosted path but does not change its measured accuracy. See
`docs/benchmarks/REAL_PERFORMANCE_RESEARCH_V1.md`.

The 2026-09-05 live full-mixture comparison then sent the same byte-identical
20-second country, free-jazz, grunge and speed-metal excerpts through the
current DrumScribe research-beta app path and Klangio Drum2Notes. Across 459
manually annotated MDB events, current DrumScribe scored 76.42% six-family
micro F1 at 50 ms versus Drum2Notes at 79.71%. The best DrumScribe research
path reached 89.59%. It is now commercially authorized under the separate owner
approval, but still misses the 90% gate by 0.41 percentage points.
See `docs/benchmarks/MDB_REAL_LIVE_COMPARISON.md`.

A balanced follow-up processed 100 real human GMD drum performances (25 each
for rock/punk, pop/soul, funk/hip-hop and jazz/world). DrumScribe v16 reached
91.70% detailed event micro F1 at 50 ms, versus 54.45% for the open-source
DrumScript 0.2.1 alpha on the same files. Jazz/world remained below target at
89.52%. These are isolated electronic-drum recordings from the already-opened
GMD test split, so the result is a comparative detector benchmark rather than
a full-song or fresh sealed release estimate. See
`docs/benchmarks/REAL_100_GENRE_COMPETITOR_BENCHMARK.md`.

The v17 selective specialist pass adds an optional post-stack blend trained on
the licensed Groove + E-GMD train partition. It raises the existing 100-record
genre comparison from 91.70% to 91.89% detailed micro F1 at 50 ms; all four
category aggregates improve. On the opened 122-record multi-kit evaluation it
raises micro F1 from 89.82% to 89.93% and supported macro F1 from 89.18% to
89.38%. The final blend retains only closed/open hi-hat, ride and mid-tom
changes that did not regress a supported class on those comparisons. Because
both test-style sets were already open and informed this pruning, these are
post-selection regression results, not a fresh generalization estimate. Pedal
hi-hat, open hi-hat, ride bell and full-mixture separation remain blockers. See
`docs/benchmarks/GROOVE_STACKED_ARTICULATION_V17.md`.

The v18 decoder pass keeps the v17 model probabilities and resolves only
exact-frame closed/open/pedal hi-hat conflicts where the winning articulation
has a 1.25 normalized-logit lead. It raises the 100-record detailed micro F1
from 91.89% to 91.95%, with global gains for all three affected hi-hat classes.
On the opened 122-record multi-kit suite, micro F1 moves from 89.93% to 90.00%
and supported macro F1 from 89.38% to 89.44%; all affected classes improve. A
focal-loss fine-tune and broader family decoders were measured and rejected.
These are still opened, post-selection isolated-drum results rather than a
fresh full-song generalization estimate. See
`docs/benchmarks/GROOVE_STACKED_ARTICULATION_V18.md`.

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
