# MDB Drums benchmark: MusicDelta_Beatles

Date: 2026-08-30

Application revision: accuracy work following baseline commit `26edba3`

Runtime: `demucs-isolated-v5` (`htdemucs_ft`) + `research-spectral-v2` + `research-beat-this-v1`

## Result

**DrumScribe did not produce an exact match to the reference drum notation.**

The accuracy passes materially improve the first draft. The neural timing pass places every emitted onset on an exact reference notation slot and reproduces the annotated tempo, but it still does not recover every reference event and is not accurate enough to claim an exact or release-quality transcription.

| Metric | Baseline | Detector pass | Neural timing E2E |
| --- | ---: | ---: | ---: |
| Reference events | 154 | 154 | 154 |
| DrumScribe events | 102 | 99 | 100 |
| Class-aware precision / recall / F1 at 50 ms | 0.667 / 0.442 / 0.531 | **0.949 / 0.610 / 0.743** | 0.940 / 0.610 / 0.740 |
| Class-aware precision / recall / F1 at 20 ms | 0.569 / 0.377 / 0.453 | 0.919 / 0.591 / 0.719 | **0.920 / 0.597 / 0.724** |
| Onset-only precision / recall / F1 at 50 ms | 1.000 / 0.662 / 0.797 | 1.000 / 0.643 / 0.783 | 1.000 / 0.649 / 0.787 |
| Exact notated class+slot precision / recall / F1 | 0.069 / 0.045 / 0.055 | 0.838 / 0.539 / 0.656 | **0.940 / 0.610 / 0.740** |
| Exact notated slot-only precision / recall / F1 | 0.373 / 0.247 / 0.297 | 0.879 / 0.565 / 0.688 | **1.000 / 0.649 / 0.787** |
| Reference / generated tempo | 111.11 / 112.35 BPM | 111.11 / 112.35 BPM | **111.11 / 111.11 BPM** |
| Drum-stem SI-SDR | -2.02 dB | **-1.89 dB** | -1.90 dB |
| Drum-stem waveform correlation | 0.621 | **0.627** | 0.626 |

### Instrument results at 50 ms

| MDB class | Reference | Predicted | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Kick | 47 | 47 | 46 | 1 | 1 | 0.979 | 0.979 | 0.979 |
| Snare | 45 | 34 | 32 | 2 | 13 | 0.941 | 0.711 | 0.810 |
| Hi-hat | 0 | 3 | 0 | 3 | 0 | 0.000 | n/a | 0.000 |
| Toms | 30 | 16 | 16 | 0 | 14 | 1.000 | 0.533 | 0.696 |
| Cymbals | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| Other percussion | 32 | 0 | 0 | 0 | 32 | n/a | 0.000 | 0.000 |

All 100 emitted hits remain close to a real annotated onset within 50 ms. The expanded physical-feature classifier recognizes toms and sharply reduces snare/hi-hat confusion while retaining a conservative onset gate. Recall is still limited: this recording's tambourine often lands within milliseconds of a snare, and the research path does not recover those 32 separate annotations.

The notation gain comes from neural beat and downbeat tracking on the full mix. The complete observed piecewise beat map, inferred meter, and bar-one offset reach quantization instead of being flattened to one BPM. Direct beat evaluation on this track measured 1.000 beat F1 and 1.000 downbeat F1 at 50 ms. Automatic drafts favor readable quarter/eighth/sixteenth and eighth-triplet grids; the editor still permits finer manual snapping.

## Cross-style regression

The same conservative detector was also evaluated against all 23 MDB Drums isolated reference stems (7,994 annotations) without changing the number of onset candidates:

| Metric | Baseline | Accuracy pass |
| --- | ---: | ---: |
| Aggregate class precision | 0.647 | **0.804** |
| Aggregate class recall | 0.387 | **0.480** |
| Aggregate class F1 | 0.484 | **0.601** |

This is a breadth regression over rock, pop, metal, country, reggae, and multiple jazz styles. It is not an independent unseen test set: the corpus was inspected while designing the deterministic feature rules, so these numbers must not be presented as a production model generalization claim.

## Local ADTOF recall experiment

The process-isolated ADTOF PyTorch baseline was run locally against the same
`htdemucs_ft` stem with its published five-class thresholds. It emitted 139 hits:
47 kick, 32 snare, 35 tom and 25 hi-hat. At 50 ms it measured 0.676 precision,
0.610 recall and 0.642 F1. Recall therefore did not improve over the selected
spectral pass, while precision fell from 0.940 and F1 fell from 0.740. Kick F1 was
0.979 and snare F1 was 0.831, but tom F1 fell to 0.492 and the five-class model
cannot represent this track's 32 tambourine events.

This is a useful negative result: ADTOF is not selected for the application stack.
The checkout/weights remain local and ignored, and its non-commercial/unlicensed
distribution constraints independently prohibit production deployment.

## YourMT3+ full-mixture A/B experiment

The `YPTF.MoE+Multi (noPS)` checkpoint was hash-verified as
`ae38e415c79efd5592dcb9b658cdb99ddb11d4c4e1eaa364cab04a052473fc25` and run
directly on the same 36.37-second full mix. The process-isolated bridge retained
only General MIDI drum-channel events and emitted 163 hits. At 50 ms it measured
0.534 precision, 0.565 recall and 0.549 F1, so it does not replace the selected
spectral detector on this track.

The per-class result is still useful: kick precision/recall/F1 was
0.958/0.979/0.968 and snare was 0.950/0.844/0.894, improving snare recall over
the spectral pass's 0.711. Tom recall fell to 0.100, extra cymbal/low-tom events
reduced aggregate precision, and no tambourine was recovered. A future ensemble
may evaluate calibrated YourMT3+ snare evidence, but it must win on a separately
held-out bakeoff before selection. The local CPU inference took about 70 seconds
after model loading/cache warm-up.

## Test material

`MusicDelta_Beatles` is a 36.37-second, full-band Beatles-style Music Delta research recording—not a copyrighted Beatles master. MDB Drums supplies the full mix, isolated drum recording, beat grid, and manually reviewed onset labels. The local benchmark copy is used only for non-commercial quality evaluation under the dataset's CC BY-NC-SA terms and remains Git-ignored.

Reference class distribution:

- 47 kick events
- 45 snare events
- 30 tom events
- 32 other-percussion events

Reference files:

- `data/benchmark-mdb-beatles/MusicDelta_Beatles_MIX.wav`
- `data/benchmark-mdb-beatles/MusicDelta_Beatles_Drum.wav`
- `data/benchmark-mdb-beatles/MusicDelta_Beatles_class.txt`
- `data/benchmark-mdb-beatles/MusicDelta_Beatles_MIX.beats`

Reference hashes:

- Events SHA-256: `228aa364e124421875d8a23c9136e9a0342cd26196c0626e94d73eb8636e8ffb`
- Drum audio SHA-256: `397230a78da321ad499df6aef31f09cfb58eb6048c85ecec0f2468b4a55da597`

## End-to-end path exercised

1. Uploaded the full stereo mix through the real browser upload page.
2. Confirmed recording rights and created an anonymous private project.
3. Transferred the audio using a signed Neon Object Storage upload.
4. Ran the durable normalization, fine-tuned Demucs isolation, spectral transcription, neural full-mix beat/downbeat tracking, piecewise quantization, and score-generation pipeline.
5. Opened the rendered drum editor and verified 100 notation events.
6. Downloaded the private isolated drum stem.
7. Generated and signature-checked MIDI, MusicXML, and PDF exports.
8. Captured the rendered editor and stored the generated events for scoring.
9. Soft-deleted the project and verified that every signed artifact URL was revoked.

The neural-timing automated browser journey passed in 2.7 minutes.

Baseline artifacts are under `data/benchmark-mdb-beatles/output/`; detector-pass artifacts are under `data/benchmark-mdb-beatles/output-v2/`; neural-timing artifacts are under `data/benchmark-mdb-beatles/output-v3/`. All are local and Git-ignored. Each directory contains the machine-readable score, rendered editor, isolated stem, and all three exports.

## Scoring method

- Raw onset evaluation uses one-to-one matching with the standard 50 ms window, plus a stricter 20 ms view.
- Class-aware scoring maps DrumScribe's detailed instrument names to MDB's six top-level classes.
- Exact notation scoring maps each reference onset to the closest sixteenth-note slot using MDB's annotated beat grid, then requires the generated measure, beat slot, and class to match exactly.
- Source separation uses scale-invariant SDR and waveform correlation against the isolated reference drum recording after mono conversion and length alignment.
- Hashes of both references and predictions are saved with the JSON result so the run is auditable.

## Engineering decision

Do not treat the improved local research path as production transcription quality. It remains behind the existing production safety gate because the Demucs weight/training-data rights are not cleared for the commercial deployment and the deterministic classifier still has material recall gaps. ADTOF was rejected on both quality and licensing grounds; YourMT3+ remains an unselected A/B backend because aggregate quality regressed and its code/checkpoint/training-data rights are unresolved.

The next model iteration should be accepted only after it:

1. Recovers layered/near-simultaneous events rather than selecting one class per broadband onset.
2. Distinguishes open/closed/pedal hi-hat, ride/crash, and side-stick/tambourine from licensed model output.
3. Validates neural beat/downbeat tracking across a separately held-out, metrically diverse corpus rather than relying on this single track.
4. Clears a commercial transcription/separation provider contract or replaces research weights with fully documented commercially licensed weights.
5. Passes a separately held-out, rights-cleared evaluation set with predeclared release thresholds.

## Reproduction

The browser harness is `apps/web/e2e/benchmark-mdb.spec.ts`. The deterministic scorer is `scripts/score_drum_benchmark.py`. Both are opt-in and require locally downloaded, rights-cleared benchmark data.
