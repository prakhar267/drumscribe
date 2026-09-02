# DrumScribe hard-metal market benchmark

Run date: 2 September 2026  
Systems: DrumScribe versus Klangio Drum2Notes public demo  
Test status: sealed after references were frozen; no post-test tuning

## Decision

DrumScribe does **not** reach 90% accuracy on this hard-metal probe. Its primary score is **65.1% family-level event F1 at ±20 ms**, compared with **74.6% for Drum2Notes**. DrumScribe wins 2 of 10 tracks on that metric and trails by 9.6 percentage points overall.

This result is useful but is not yet a population estimate for commercial releases. The ten tracks are new, rights-cleared, approximately 19-second original hard-metal fixtures rendered with one licensed acoustic kit and code-generated distorted guitar/bass. They are not Metallica, Linkin Park, or other copyrighted masters.

## Headline results

| Metric | DrumScribe | Drum2Notes | Difference |
|---|---:|---:|---:|
| Detailed 14-class event F1, ±20 ms | 53.3% | 61.1% | -7.8 pp |
| Family 6-class event F1, ±20 ms — primary | 65.1% | 74.6% | -9.6 pp |
| Core kick/snare/hi-hat event F1, ±20 ms | 72.6% | 75.9% | -3.3 pp |
| Detailed 14-class event F1, ±50 ms | 53.8% | 63.2% | -9.4 pp |
| Family 6-class event F1, ±50 ms | 65.6% | 77.9% | -12.2 pp |
| Core kick/snare/hi-hat event F1, ±50 ms | 73.3% | 78.5% | -5.2 pp |
| Exact family+notation-slot F1 | 60.9% | 72.5% | -11.5 pp |
| Tempo mean absolute error | **2.48 BPM** | 15.20 BPM | DrumScribe better |
| Drum isolation SI-SDR | 9.61 dB | Not exposed | — |
| Drum isolation correlation | 0.946 | Not exposed | — |

F1 is `2 × TP / (2 × TP + FP + FN)`. It measures both missed notes and extra notes; it is not a subjective quality rating. The family taxonomy groups cymbal articulations and tom pitches so the comparison does not reward one product for exposing a finer label set.

## Per-track comparison

The primary column is family 6-class F1 at ±20 ms. “Notation” requires the correct family on the exact sixteenth-note score slot.

| Track | Style | BPM | Reference events | DrumScribe | Drum2Notes | DrumScribe notation | Drum2Notes notation |
|---|---|---:|---:|---:|---:|---:|---:|
| Chromium Assault | Thrash | 198 | 320 | 60.8% | **68.3%** | 60.8% | **68.3%** |
| Concrete Pulse | Nu-metal | 104 | 132 | 62.5% | **85.7%** | 62.5% | **85.7%** |
| Fractured Signal | Metalcore | 156 | 265 | 68.0% | **82.2%** | 68.4% | **82.2%** |
| Terminal Velocity | Death metal | 220 | 399 | 65.1% | **69.0%** | **58.9%** | 46.7% |
| Gravity Well | Doom metal | 72 | 55 | **59.7%** | 57.4% | **59.7%** | 34.8% |
| Iron Circuit | Groove metal | 122 | 165 | 61.1% | **87.5%** | 61.1% | **87.5%** |
| Machine Ritual | Industrial metal | 128 | 293 | 59.6% | **74.2%** | 59.6% | **74.2%** |
| Odd Horizon | Progressive metal | 138 | 173 | 59.4% | **87.4%** | 59.9% | **87.4%** |
| Solar Vanguard | Power metal | 184 | 326 | **74.7%** | 69.0% | 53.1% | **81.3%** |
| Rusted Crown | Hardcore/d-beat | 192 | 270 | 70.6% | **71.1%** | 66.4% | **74.2%** |

Micro-averaged totals weight every reference event equally. The unweighted mean of the ten primary track scores is 64.2% for DrumScribe and 75.2% for Drum2Notes.

## What failed

DrumScribe's strongest family-level class is kick at 84.4% F1. The largest remaining errors are hi-hat recall, snare precision, tom-family false positives, and missing tambourine. The model also confuses detailed hi-hat and tom articulations, which is why the 14-class score falls to 53.3% even though its onset timing is tight.

Tempo tracking is already a strength. DrumScribe's 2.48 BPM mean error beats Drum2Notes' 15.20 BPM; the competitor made a 113 BPM half/double-tempo error on the 220 BPM death-metal fixture. Drum isolation is usable but not clean enough to remove every distorted-guitar transient before classification.

The current evidence does not support a “90% accurate” sales claim. A defensible launch claim must identify the metric, taxonomy, tolerance, and evaluation set.

## Method

1. Generated ten original full mixes spanning thrash, nu-metal, metalcore, death metal, doom metal, groove metal, industrial metal, progressive metal, power metal, and hardcore/d-beat.
2. Froze 2,398 exact reference events before either system ran. Each track has reference JSON, MIDI, MusicXML, audio, and rendered PDF notation.
3. Processed the identical full mixes with DrumScribe: HTDemucs-ft isolation, the frozen `groove-stacked-articulation-v16` seven-checkpoint detector, and Beat This timing.
4. Submitted the identical full mixes to the [Drum2Notes public demo](https://klang.io/drum2notes/) using Single-Instrument → Drums → All, with automatic advanced settings.
5. Decoded the structured notation used by the public result viewer. No paid exports were accessed and no competitor result identifiers are published.
6. Scored both systems with the same one-to-one matcher at ±20 ms and ±50 ms, plus exact score-slot matching, across detailed, family, and core taxonomies.

## Validation and reproducibility

- All 10 audio files are 18.64–20.00 seconds, 44.1 kHz, and unclipped.
- All 10 references passed event-bound, duration, hash, MIDI, MusicXML, and PDF generation checks.
- All 10 Drum2Notes payloads are valid version-3, single-part scores with matching 18–20 second audio duration and unique SHA-256 hashes.
- Aggregate TP/FP/FN counts equal the sum of the ten per-track counts. F1 was independently recomputed from those counts.
- A floating-point boundary issue found during validation was fixed by aggregating per-track confusion counts rather than adding artificial time offsets.
- Suite manifest SHA-256: `8ef3a656478f2fee09c41bb2b40ce7bf791284503a5c1e9430c0cb0f559dd18e`.
- Machine-readable results: [`benchmark-result.json`](benchmark-result.json).
- Reproducible generator/scorer: [`scripts/run_hard_metal_market_benchmark.py`](../../scripts/run_hard_metal_market_benchmark.py).

## Reference notation

- [Chromium Assault](tracks/01-thrash-assault/reference.pdf)
- [Concrete Pulse](tracks/02-nu-metal-breakdown/reference.pdf)
- [Fractured Signal](tracks/03-metalcore-drive/reference.pdf)
- [Terminal Velocity](tracks/04-death-metal-blast/reference.pdf)
- [Gravity Well](tracks/05-doom-weight/reference.pdf)
- [Iron Circuit](tracks/06-groove-metal/reference.pdf)
- [Machine Ritual](tracks/07-industrial-metal/reference.pdf)
- [Odd Horizon](tracks/08-progressive-metal/reference.pdf)
- [Solar Vanguard](tracks/09-power-metal-gallop/reference.pdf)
- [Rusted Crown](tracks/10-hardcore-dbeat/reference.pdf)

## Scope limits

- Synthetic fixtures provide exact ground truth but do not reproduce every production, mastering, room, drummer, or kit condition in released music.
- Only one competitor and one public-demo configuration were tested.
- Drum2Notes' internal model version is not disclosed, so this records observed service behavior on 2 September 2026.
- Demucs and Beat This are research dependencies whose checkpoint/training-data production licensing still needs resolution before a commercial deployment.
- The next honest gate is a preregistered, rights-cleared real-recording set from multiple kits and drummers; it must remain untouched during model tuning.

## Sources

- Klangio, [Drum2Notes product and public demo](https://klang.io/drum2notes/).
- CPJKU, [Beat This paper](https://arxiv.org/html/2407.21658) and [repository](https://github.com/CPJKU/beat_this).
- Meta Research, [Demucs repository](https://github.com/facebookresearch/demucs).
- FreePats, [MuldjordKit acoustic drum samples](https://freepats.zenvoid.org/Percussion/acoustic-drum-kits.html).
- Local benchmark result and ten frozen reference scores linked above.
