# RWC novel-model v22 evaluation

Date: 2026-09-05

## Decision

The 90% target was **not achieved** on the fixed RWC Popular benchmark. The
best secondary 39-song result remains **68.16% detailed-event micro F1 at
±50 ms**. That is 21.84 percentage points below 90%.

No reference labels, matching tolerance, selected songs, or empty/hard tracks
were changed. Both new candidates were selected on the 50-song development
partition and then evaluated with frozen settings on the 39-song secondary
partition. That secondary partition was opened during v19 research and is not
a sealed holdout.

The rights-cleared-training v18 candidate scores **50.25%** on the same 39
songs. Research v20 scores **63.08%**, but it was calibrated against RWC's
CC BY-NC labels and is not commercially approved. The 68.16% research result
also uses ADTOF-derived predictions and is not commercially deployable under
[ADTOF's published non-commercial license](https://github.com/MZehren/ADTOF)
without a separate commercial grant. RWC audio and labels are evaluation
evidence, not production training assets.

## Novel experiments

| Candidate | Development detailed F1 @50 ms | Secondary-39 detailed F1 @50 ms | Decision |
| --- | ---: | ---: | --- |
| Frozen ADTOF + 14-class embedding-head reference | 65.71% | **68.16%** | Keep as research reference |
| Beat-synchronous repetition repair | **66.08%** | 67.68% | Reject: development gain did not transfer |
| Inverse Drum Machine standalone | 51.13% | 56.61% | Reject |
| IDM onset proposals + DrumScribe class posteriors | **65.83%** | 68.14% | Reject: below the frozen reference |

The repetition repair used Beat This beats/downbeats to infer repeating
instrument patterns over 1, 2, 4, and 8 beats. It could add or replace events
only when a phase repeated with sufficient support. This helped development by
0.36 points but hurt the fixed secondary partition by 0.48 points.

The [Inverse Drum Machine](https://github.com/bernardo-torres/inverse-drum-machine)
is a genuinely different analysis-by-synthesis model that jointly predicts
onsets and synthesizes drum one-shots. Its Apache-2.0 checkpoint was run across
all 89 clips. Its onset proposals improved development by 0.11 points after
DrumScribe reclassified them, but reduced the secondary result by 0.014 points.
The paper itself says its transcription evaluation is not intended as a
state-of-the-art ADT comparison and attributes its strong internal results in
part to controlled, low-diversity conditions
([paper](https://arxiv.org/html/2505.03337)).

[ADT-STR](https://github.com/pier-maker92/ADT_STR) was inspected but could not
be benchmarked: its public repository contains training and inference code but
no pretrained checkpoint. [Noise-to-Notes](https://arxiv.org/abs/2509.21739)
describes diffusion-based refinement but does not provide a runnable public
artifact suitable for this evaluation.

## Same-benchmark open-system comparison

Every numeric row below was scored on the same 39 RWC source excerpts against
the same performance-MIDI references, with one-to-one class-aware matching at
±50 ms. Input representations differ where noted: end-to-end systems begin
from the full mix, while research backends may receive its derived drum stem.

| System | Detailed-14 F1 | Family-6 F1 | Core-3 F1 | Class-agnostic onset F1 | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| DrumScribe research fusion | **68.16%** | 70.91% | 77.65% | 75.09% | Research-only ADTOF dependency |
| ADTOF | 67.06% | **72.93%** | **79.44%** | **76.08%** | Five output classes; non-commercial license |
| DrumScribe research v20 | 63.08% | 66.23% | 72.29% | 73.48% | RWC-calibrated; not commercially approved |
| Inverse Drum Machine | 56.61% | 61.58% | 71.12% | 71.11% | Nine classes; Apache-2.0 |
| DrumScribe v18 | 50.25% | 55.70% | 60.65% | 64.86% | Rights-cleared training; not broad-production validated |
| OaF Drums | 38.08% | 47.06% | 53.15% | 58.84% | Isolated-stem research baseline |
| DrumScript 0.2.1 | 16.45% | 25.92% | 33.52% | 62.61% | Same full-mix input; 39/39 completed |

For diagnosis only, DrumScript reached 48.71% detailed F1 when given
DrumScribe's precomputed HTDemucs-ft drum stems instead of the same full mix.
That is not the equal-input leaderboard score. DrumScript describes itself as
an alpha deterministic classifier and lists broader full-kit benchmarking as
future work
([repository](https://github.com/DrumScript/DrumScript),
[benchmark status](https://github.com/DrumScript/DrumScript/blob/main/benchmarks/README.md)).

The 2026 open-source [STRUM](https://github.com/opria123/strum) project is a
promising two-stage CRNN/ensemble design, but it could not be run here: its
repository and releases do not publish the required checkpoints, and its README
states roughly 6 GB is required. Its published 83.8% drum figure uses 29
pre-screened game-chart songs, ±100 ms matching, and a per-song offset search;
it is therefore not interchangeable with this ±50 ms result.

## Five product competitors

There is no honest five-product numeric leaderboard for this RWC partition.
Four services do not expose the batch predictions and machine-readable exports
needed for this protocol, and several require payment, sign-in, or a rights
attestation. Their marketing statements are not substituted for measurements.

| Product | Public numeric accuracy claim | Same RWC-39 score |
| --- | --- | ---: |
| Klangio Drum2Notes | No comparable percentage; calls its output "unparalleled accuracy" | Not measured |
| Drumscrib | Historical claim of detecting more than 95% of notes on average; current help explicitly says it is beta and has no benchmark | Not measured |
| PlayDrumsOnline | No numeric accuracy claim; one free transcription and private upload is paid | Not measured |
| Drum AI | No public numeric accuracy claim on the accessible transcription page | Not measured |
| DrumScript | No broad production-accuracy claim | **16.45%** |

Klangio currently permits unlimited free 20-second previews but does not expose
an evaluation API or free MIDI/MusicXML exports
([official plans](https://klang.io/help/compare-apps-and-subscriptions/)).
Drumscrib's own help page says the service still has errors and that claiming a
state-of-the-art benchmark would be disingenuous
([official help](https://drumscrib.com/en/help)); its old “more than 95%”
statement is note recall, not precision or F1. PlayDrumsOnline's official page
limits the free plan to one transcription and requires Premium for MP3 upload
([official page](https://www.playdrumsonline.com/create)).

## What is required to pursue 90%

The remaining gap is too large for another threshold or quantization pass. A
credible attempt needs a new production-owned training cycle:

1. Build a rights-cleared, human-annotated full-mixture corpus with all 14
   output classes, deliberately including quiet hats, detailed toms, cymbal
   articulations, metal, jazz, soft pop, live rooms, and dense mixes.
2. Train a two-stage system: a high-recall onset proposal model followed by a
   multi-view classifier ensemble using full mix, drum stem, and local spectral
   context. Add hard negatives mined from vocals, distorted guitars, and
   separation bleed.
3. Add calibrated routing that can ignore a bad separated stem instead of
   forcing every song through the same view.
4. Freeze two independent, rights-cleared song-level holdouts. Require at least
   90% detailed micro F1 at ±50 ms on both, plus per-genre and per-class floors,
   before making a sales claim.

Until those gates pass, the accurate statement is: **50.25% for the
rights-cleared-training v18 candidate and 68.16% for the best research-only
fusion on this RWC secondary benchmark—not 90%.**

Compact machine-readable evidence is in
`docs/benchmarks/data/RWC_NOVEL_MODEL_V22.json`.
