# Recall fusion v1/v2 and live comparison

Date completed: 2026-09-05

DrumScribe now combines its first-party stacked articulation model with the
commercially authorized ADTOF detector. Full musical mixtures use a separate
class-specific fusion of the direct full-mix activations and the aligned
`htdemucs_ft` drum-stem activations. The production pipeline passes both views
to the model runner instead of discarding the original mix.

Recall fusion v2 adds a separate high-precision profile for isolated acoustic
drum recordings. It does not replace the electronic-kit ensemble or alter the
full-mixture route.

## Result summary

| Evaluation | Status | DrumScribe | Drum2Notes | Difference |
| --- | --- | ---: | ---: | ---: |
| 20 GMD electronic-drum performances, five families | Frozen same-audio; 17 prior overlaps | **90.63%** | 78.66% | **+11.97** |
| 14 IDMT RealDrum loops, first run, three families | Independent first run | 72.70% | **92.94%** | -20.25 |
| Same 14 IDMT loops, acoustic profile v2 | Opened-corpus improvement | **97.21%** | 92.94% | **+4.27** |
| 4 STAR full musical mixtures, five families | Opened development regression | **85.07%** | 59.85% | **+25.21** |

All percentages are class-aware micro F1 at 50 ms. These rows measure different
input conditions and taxonomies and must not be averaged into one product-wide
accuracy number.

## Frozen same-audio result

The primary comparison contains 20 GMD test-split audio files, five from each
broad style group. The manifest was written before the new decoder or
Drum2Notes was run, and selection did not use note annotations. Both systems
received the same PCM WAV bytes. All 20 new Drum2Notes public-demo jobs
completed successfully. A post-run provenance audit found that 17 of these 20
source performances had appeared in older first-party experiments, so this is
a frozen same-audio comparison, not a completely unseen corpus.

The primary metric is five-family, one-to-one onset F1 at 50 ms.

| Metric | DrumScribe | Drum2Notes | Lead |
| --- | ---: | ---: | ---: |
| Five-family micro F1 | **90.63%** | 78.66% | **+11.97 points** |
| Precision | **89.97%** | 87.46% | **+2.51 points** |
| Recall | **91.30%** | 71.46% | **+19.84 points** |
| Exact-articulation micro F1 | **89.25%** | 64.80% | **+24.45 points** |
| Mean matched-onset error | **5.46 ms** | 18.03 ms | **12.57 ms lower** |

DrumScribe produced 2,959 true positives, 330 false positives and 282 false
negatives. Drum2Notes produced 2,316 true positives, 332 false positives and
925 false negatives.

## Genre groups

| Group | Inputs | DrumScribe | Drum2Notes |
| --- | ---: | ---: | ---: |
| Heavy rock / punk | 5 | **92.25%** | 77.17% |
| Pop / soul | 5 | **96.91%** | 91.82% |
| Funk / hip-hop | 5 | **88.66%** | 85.89% |
| Jazz / world | 5 | **86.71%** | 62.58% |

The progressive-rock recording scored **93.41%** for DrumScribe versus
76.92% for Drum2Notes. This is a new recording, separate from the earlier
progressive development item that scored 67.72% with the old decoder.

## Instrument families

| Family | DrumScribe | Drum2Notes |
| --- | ---: | ---: |
| Kick | **95.16%** | 80.43% |
| Snare | **89.25%** | 65.04% |
| Hi-hat | **88.20%** | 83.12% |
| Toms | **93.29%** | 76.03% |
| Cymbals | **95.63%** | 91.67% |

The detailed-class evaluation also verifies that the runner emits individual
tom and cymbal articulations rather than only family labels. Mid tom reached
98.51%, floor tom 92.45%, high tom 87.27%, ride 95.54%, and ride bell 92.31%.
Crash remains weak at 55.81%, and open/pedal hi-hat remain weak at 64.29% and
59.80%. The 89.25% detailed aggregate must not be presented as 90% exact-note
accuracy.

## Full-mixture regression

The four previously opened STAR preview mixtures remain a development
regression suite, not a sealed result. On the exact same mixtures, direct plus
Demucs-stem ADTOF activation fusion improved DrumScribe from 80.47% to
**85.07%**. Drum2Notes scored 59.85% on those files. Full-mixture kick reached
98.84% and snare 95.89%, while separated-mixture toms remained weak at 40.00%.

## Independent acoustic-drum audit and v2 correction

After the GMD provenance overlap was discovered, all 14 polyphonic `RealDrum`
recordings from IDMT-SMT-Drums V2 were downloaded from the official release.
The selection manifest and source hashes were frozen before either product ran,
and the manual SVL labels were parsed only after both systems completed. The
corpus had not previously appeared in this repository. Both products received
the same WAV bytes and all 14 live Drum2Notes jobs completed successfully.

The first run found a genuine domain failure: v1 reached only **72.70%**, while
Drum2Notes reached **92.94%**. DrumScribe recall was 97.73%, but precision was
57.87%; the electronic-kit ensemble produced 551 false-positive snare events.
This failed first result remains preserved as the independent evidence.

The opened-corpus diagnosis showed that ADTOF's acoustic detector was strong
while the electronic articulation specialist was causing the extra triggers.
V2 therefore adds an explicit isolated-acoustic profile with class-specific
peak thresholds, a snare family-margin guard and 15 ms latency compensation.
It also preserves intentional kick/hi-hat unisons instead of applying the
separated-song slow-swing suppression. On the same now-opened corpus, the
corrected profile measured:

| Metric at 50 ms | DrumScribe v2 acoustic | Drum2Notes |
| --- | ---: | ---: |
| Three-family micro F1 | **97.21%** | 92.94% |
| Precision | **95.95%** | 90.49% |
| Recall | **98.51%** | 95.53% |
| Supported macro F1 | **97.10%** | 91.79% |
| Mean matched-onset error | **10.15 ms** | 14.88 ms |
| Kick F1 | **98.49%** | 94.18% |
| Snare F1 | **95.51%** | 86.07% |
| Hi-hat F1 | **97.32%** | 95.11% |

This demonstrates the fix on the development corpus, but it is not a second
independent validation: the IDMT first-run labels informed the acoustic profile.
IDMT is published for evaluation under CC BY-NC-ND 4.0, so its audio remains
local research material and is not included in product training or distribution.
An external acoustic-drum corpus must confirm v2 before making a general claim.

## What changed

1. The first-party stacked model supplies higher-recall snare and tom onsets and
   preserves cross-stick, four tom sizes, hi-hat articulations, crash, ride and
   ride-bell labels.
2. ADTOF supplies an independent onset view. Hi-hat and cymbal events are
   merged only after 50 ms family-aware deduplication.
3. Low-confidence recovery requires agreement between ADTOF and the first-party
   model. Tom and hi-hat recovery additionally requires equal-period support on
   both sides of the candidate. A unilateral rhythm-completion rule was tested
   and rejected because it reduced F1.
4. Full mixtures use class-specific direct/stem weights. This avoids making
   separation the single point of failure when bleed masks a quieter hit.
5. Every component and decoder parameter is hash-pinned. The frozen GMD result
   uses `ml/configs/drumscribe-recall-fusion-v1.json`; the acoustic profile is
   in `ml/configs/drumscribe-recall-fusion-v2.json`. The runner fails closed if
   a pinned component changes.
6. The acoustic route uses generic five-family labels. Detailed cross-stick,
   hi-hat articulation, tom-size and cymbal subtype quality still comes from the
   electronic ensemble and has not been independently verified on acoustic kits.

## Evidence boundary

- The selection and live jobs were frozen before this decoder was scored, but
  17 source performances overlap older benchmark/model-selection work. This is
  not an organization-wide unseen or independent third-party audit.
- GMD contains real human electronic-drum performances, not complete commercial
  song mixtures. The STAR preview is the full-mixture regression, but it has
  only four previously opened items.
- The family result clears 90%; the exact-articulation aggregate and two genre
  groups do not. This therefore supports a bounded “90.63% on our locked
  20-recording five-family comparison” statement, not a universal 90% claim.
- The result does not pass the separate 99% release gate, which requires at
  least 100 recordings, 10 hours, full mixtures, every class above 99%, and
  notation/export measurements.
- The IDMT first run is the only completely new-corpus result in this report,
  and it failed at 72.70%. The 97.21% v2 measurement is explicitly an
  opened-corpus improvement result, not sealed generalization evidence.

Frozen manifest SHA-256:
`9c96901ab269fce9f1af46cc5358e9a12513ee5ffaf6a542bd7f52b546465885`.

Raw result SHA-256:
`a2502468c942b4009f1e0c05a0cf8c5fe4615b8cdd610a1ae42221c4fbb39aa3`.

IDMT first-run manifest SHA-256:
`9043fa5e5e08d009a5384938b2759857626d17ad2ab3c7004f3bd8e53b73288e`.

IDMT first-run result SHA-256:
`e1270264968db1e721e18e70965249a914a0150f36b8dec1bb82954681a9da5d`.

IDMT opened v2 result SHA-256:
`cf37c35da75ce16b5d82ee6068eb59971646b3306d6521fa6a129265eb1136f6`.

Recall-fusion v2 config SHA-256:
`bda7d333fe4901a26a06d45ea07eea0bb5659fe13b744852dc32b6f72989f1df`.
