# Real-performance accuracy research v1

Date completed: 2026-09-03

Decision: **the current research stack clears 90% on the two opened,
rights-cleared synthetic development probes, but it does not clear 90% on an
independent set of real human performances.** The best full-mixture MDB Drums
result is **82.98% six-family micro F1 at 50 ms**. A broad “90% accurate” or
“ready to sell at 90%” claim is therefore not supported.

## Results that answer the earlier regressions

| Evaluation | Earlier | Current | Metric | Status |
| --- | ---: | ---: | --- | --- |
| Ten supported-kit hard-metal tracks | 78.13% | **96.43%** | family micro F1 at 20 ms | opened development probe |
| Quiet Horizon soft song | 51.85% | **97.33%** | family micro F1 at 20 ms | opened development probe; research-only ADTOF |
| Eleven real full mixtures | — | **82.98%** | family micro F1 at 50 ms | independent MDB research test |
| Eleven ideal real drum stems | — | **85.01%** | family micro F1 at 50 ms | diagnostic upper bound |

The metal development suite contains 2,391 events. Current precision is
98.64%, recall is 94.31%, family macro F1 is 94.84%, and every track is above
92.52%. Detailed-class micro F1 is 94.80%, but detailed-class macro F1 is only
68.43% because rare crash, cross-stick, ride-bell, open-hi-hat and individual
tom articulations remain weak.

The soft-song result contains 94 references and 93 predictions. It has 97.85%
precision, 96.81% recall and 96.98% family macro F1. This test had already been
opened before the ADTOF/completion path was selected, so it measures a repaired
regression rather than generalization.

## Independent real-performance test

MDB Drums contains real human performances and manually reviewed annotations.
The official MIREX test split was not used for training or decoder calibration.
It is CC BY-NC-SA 4.0 and is used locally for research only.

| Input and detector | F1 at 20 ms | F1 at 50 ms |
| --- | ---: | ---: |
| Ideal isolated drum stem → ADTOF | 78.73% | **85.01%** |
| Full mix → `htdemucs_ft` → ADTOF | 74.57% | **82.98%** |
| Full mix → ADTOF directly | 72.31% | 78.07% |
| Ideal drum stem → first-party stacked v16 | — | 74.38% |
| Ideal drum stem → YourMT3+ | — | 71.18% |

The separated full-mixture path exceeds 90% on Gospel (94.01%), Grunge
(91.96%), Hendrix (100%) and Speed Metal (93.24%), but not across all genres.
Beatles (64.38%), country/side-stick (63.55%) and swing jazz (69.77%) expose the
largest domain and taxonomy gaps. At 50 ms, kick reaches 95.35% F1, snare
82.53%, cymbal 84.39%, hi-hat 77.64%, tom 32.89%, and MDB's “other” family 0%.

## Engineering changes

The accuracy pass made four bounded changes:

1. Repeated hi-hat/ride templates now require recurrence across measures, so
   isolated cymbal errors cannot force dense sixteenth-note output.
2. Low-confidence generic cymbals are no longer duplicated as both a preserved
   crash and an inferred ride.
3. If no repeated texture is proved, completion now preserves detector hits.
   Previously it deleted them even though it had no replacement pattern.
4. Expressive hits outside the snap window are preserved, and rhythm completion
   requires high-confidence kick anchors by default. A detector without
   calibrated probabilities therefore fails open instead of inventing a grid.

The reusable scorer records exact hashes and reports 20, 50 and 100 ms
one-to-one metrics. The supported-kit runner can now regenerate the post-opened
research fusion and explicitly labels its score as development evidence.

## Why more models did not automatically improve the score

On the same ideal drum stems, YourMT3+ reached 71.18% and the first-party v16
stack reached 74.38%, both below ADTOF's 85.01%. ADTOF parameters calibrated
only on the MDB training split reached 84.11% on the test split, also below its
published default decoder. Those alternatives were rejected rather than added
to a larger but less accurate stack.

Recent research also sets a realistic boundary. ADT-STR reports roughly 79%
average F1 on MDB's broad drum classes, not 90%, and its repository does not
provide a production-ready checkpoint. Separate-and-Detect publishes a useful
separation architecture, but its available component checkpoints total many
gigabytes and still require a complete artifact/training-data rights audit.

## Competitor comparison status

The predeclared live Drum2Notes comparison is now complete on the same first
20 seconds of Speed Metal, Grunge, Free Jazz and Country. On 459 annotated
events, the current DrumScribe app research path scores **76.42%** six-family
micro F1 at 50 ms and Drum2Notes scores **79.71%**. The best non-commercial
DrumScribe research path scores **89.59%**. All four competitor jobs completed;
no service failure or track was excluded. Both systems started from byte-identical
full-mixture excerpts. See `MDB_REAL_LIVE_COMPARISON.md` for the per-genre
results and commercial boundary.

The follow-up same-audio comparison expanded to all 11 MDB test tracks and
submitted 11 new Drum2Notes jobs. DrumScribe reached **86.55%** versus
Drum2Notes at **80.25%** six-family micro F1 at 50 ms, winning 8 of 11 tracks.
See `MDB_OWNER_APPROVED_LIVE_TEST11.md`.

The subsequent rhythm-consistency decoder removed a regular false-tom intro
and slow-swing kick/hi-hat duplicates. Fresh live target tests reached 96.15%
versus 95.00% on gospel and 78.38% versus 74.32% on swing jazz. See
`MDB_RHYTHM_DECODER_TARGET2.md` for the regression and evidence boundary.

The existing completed comparison remains the 12-track rights-cleared synthetic
suite: DrumScribe 97.35% versus Drum2Notes 65.54% at 20 ms. That result does not
answer real-song generalization.

A later 100-recording comparison on isolated GMD human performances measured
DrumScribe against DrumScript and is reported separately in
`docs/benchmarks/REAL_100_GENRE_COMPETITOR_BENCHMARK.md`.

## Commercial approval and next work

The company owner recorded a separate commercial-use grant for the pinned ADTOF
and `htdemucs_ft` artifacts under `OWNER-ATTESTATION-2026-09-05`. The public
upstream license remains unchanged; DrumScribe's production permission comes
from that separate grant. Exact artifact hashes are recorded in
`MODEL_LICENSING.md` and `docs/legal/COMMERCIAL_MODEL_RIGHTS_APPROVAL.md`.

The next path toward a defensible 90% real-song result is rights-cleared
multi-kit human data with explicit tom, side-stick, hi-hat articulation and
cymbal labels; train-only domain calibration; a commercially approved
drum-component separator; and a new sealed real-song test set. The compact
machine-readable evidence is in
`docs/benchmarks/data/REAL_PERFORMANCE_RESEARCH_V1.json`.
