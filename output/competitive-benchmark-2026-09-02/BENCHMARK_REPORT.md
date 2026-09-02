# DrumScribe live market comparison — 2026-09-02

## Result

On this controlled 200-second probe, DrumScribe v16 exceeded the live Klangio
Drum2Notes demo on every aggregate transcription metric. The main 14-class,
class-aware event F1 at ±50 ms was **92.12% for DrumScribe** and **76.87% for
Drum2Notes**.

This is a comparative probe, not a claim that DrumScribe is 92% accurate on all
commercial music. The recordings are isolated electronic-drum performances,
and this Groove test material has already been examined during internal product
development. Full-mixture separation and out-of-domain generalization remain
separate product risks.

## Like-for-like aggregate results

| Metric | DrumScribe v16 | Drum2Notes live demo | Lead |
|---|---:|---:|---:|
| Detailed 14-class event F1, ±50 ms | **92.12%** | 76.87% | +15.25 pp |
| Six-family event F1, ±50 ms | **92.94%** | 89.12% | +3.83 pp |
| Core kick/snare/hi-hat F1, ±50 ms | **92.95%** | 91.12% | +1.84 pp |
| Class-agnostic note-onset F1, ±50 ms | **93.13%** | 89.73% | +3.40 pp |
| Detailed 14-class event F1, ±20 ms | **91.12%** | 53.88% | +37.24 pp |
| Class-agnostic note-onset F1, ±20 ms | **92.19%** | 64.49% | +27.70 pp |

The narrow core-kit lead matters: Drum2Notes is competitive when kick, snare,
and all hi-hat articulations are collapsed into three broad labels. DrumScribe's
much larger detailed-score lead comes from retaining cross-stick, open/pedal
hi-hat, ride, and crash identities that the live demo often omitted or collapsed.

## Detailed class results at ±50 ms

| Class | Reference notes | DrumScribe F1 | Drum2Notes F1 |
|---|---:|---:|---:|
| Kick | 309 | **99.68%** | 95.91% |
| Snare | 348 | **89.44%** | 76.85% |
| Cross-stick | 18 | **97.14%** | 0.00% |
| Closed hi-hat | 615 | **91.09%** | 87.19% |
| Open hi-hat | 22 | **90.00%** | 0.00% |
| Pedal hi-hat | 180 | **87.05%** | 0.00% |
| Ride | 93 | **92.47%** | 0.00% |
| Crash | 4 | **100.00%** | 25.00% |

No evaluated event occurred for high/mid/low/floor tom, ride bell, or tambourine
inside these ten 20-second windows, so this run provides no evidence for those
classes.

## Per-record detailed F1 at ±50 ms

| Recording | Reference BPM | Drum2Notes BPM | DrumScribe | Drum2Notes |
|---|---:|---:|---:|---:|
| funk groove 1 | 138 | 130 | **93.79%** | 39.74% |
| soul groove 10 | 102 | 100 | **93.55%** | 92.44% |
| funk groove 2 | 105 | 103 | **89.86%** | 80.12% |
| soul groove 3 | 86 | 86 | **92.62%** | 91.33% |
| soul groove 4 | 80 | 79 | **97.92%** | 92.63% |
| funk groove 5 | 84 | 83 | **94.74%** | 82.24% |
| hip-hop groove 6 | 87 | 86 | **95.36%** | 92.31% |
| pop groove 7 | 138 | 130 | 94.87% | **96.30%** |
| rock groove 8 | 65 | 64 | **96.69%** | 81.05% |
| soul groove 9 | 105 | 103 | **73.87%** | 35.71% |

Drum2Notes' mean absolute displayed-tempo error was 2.6 BPM (median 1.5 BPM).
Its audio-aligned per-measure timestamps—not its rounded displayed BPM—were
used for onset scoring.

## Most important failure found in DrumScribe

The weakest DrumScribe item was `soul groove 9` at 73.87% detailed F1. It found
nearly all true notes (93.81% recall), but emitted 68 extra closed-hi-hat notes
alongside a passage whose reference contains pedal hi-hat. This is a concrete
articulation-family competition problem, not a timing problem: matched-event
median timing error on that item was only 3.11 ms. Preventing simultaneous
closed/pedal/open-hat duplicates is the highest-value next detector fix exposed
by this run.

## Protocol

- Inputs: the ten rights-cleared `drummer1/eval_session` recordings from the
  Google Magenta Groove MIDI Dataset official test split.
- Window: first 20.0 seconds of every recording; 200.0 seconds total.
- Reference: canonical MIDI-derived DrumScribe annotations.
- Matching: one-to-one event matching at both ±20 ms and ±50 ms.
- Competitor: each recording was submitted separately to the live Drum2Notes
  public demo using single-instrument/drums/all-kit settings. We scored the
  structured, audio-aligned note data displayed by its result viewer. No paid
  export was accessed.
- DrumScribe: frozen seven-checkpoint
  `groove-stacked-articulation-v16` configuration and frozen thresholds.
- Integrity: source audio, checkpoints, competitor results, and the frozen
  ensemble configuration are SHA-256 recorded in `benchmark-result.json`.
- Validation: 76 independent consistency and integrity checks passed after the
  run.

## Other current products

- Drumscrib cannot be measured in this run without making a purchase. Its own
  help page says it remains beta, contains errors, and does not publish a
  benchmark; an older news post's “more than 95% of notes” statement is a recall
  claim, not independently comparable F1.
- PlayDrumsOnline permits one transcription with a free account, while repeated
  uploads and exports are premium. One allowed song is not enough for this
  ten-record protocol.
- DrumAI exposes no documented quantitative benchmark or reproducible public
  evaluation result.
- DrumScript is an open-source alpha project rather than a current commercial
  product with published accuracy evidence.

Official product references:

- https://drum2notes.klang.io/
- https://drumscrib.com/en/help
- https://drumscrib.com/en/news
- https://www.playdrumsonline.com/remote
- https://www.drumai.me/
- https://github.com/DrumScript/DrumScript

