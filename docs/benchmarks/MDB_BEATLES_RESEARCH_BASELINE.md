# MDB Drums benchmark: MusicDelta_Beatles

Date: 2026-08-30

Application revision: accuracy work following baseline commit `26edba3`

Runtime: `demucs-isolated-v5` (`htdemucs_ft`) + `research-spectral-v2` + `research-librosa-beat-v2`

## Result

**DrumScribe did not produce an exact match to the reference drum notation.**

The accuracy pass materially improves the first draft, especially its precision and notated grid. It still does not recover every reference event and is not accurate enough to claim an exact or release-quality transcription.

| Metric | Baseline | Accuracy pass |
| --- | ---: | ---: |
| Reference events | 154 | 154 |
| DrumScribe events | 102 | 99 |
| Class-aware precision / recall / F1 at 50 ms | 0.667 / 0.442 / 0.531 | **0.949 / 0.610 / 0.743** |
| Class-aware precision / recall / F1 at 20 ms | 0.569 / 0.377 / 0.453 | **0.919 / 0.591 / 0.719** |
| Onset-only precision / recall / F1 at 50 ms | 1.000 / 0.662 / 0.797 | 1.000 / 0.643 / 0.783 |
| Exact notated class+slot precision / recall / F1 | 0.069 / 0.045 / 0.055 | **0.838 / 0.539 / 0.656** |
| Exact notated slot-only precision / recall / F1 | 0.373 / 0.247 / 0.297 | **0.879 / 0.565 / 0.688** |
| Reference / generated tempo | 111.11 / 112.35 BPM | 111.11 / 112.35 BPM |
| Drum-stem SI-SDR | -2.02 dB | **-1.89 dB** |
| Drum-stem waveform correlation | 0.621 | **0.627** |

### Instrument results at 50 ms

| MDB class | Reference | Predicted | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Kick | 47 | 47 | 46 | 1 | 1 | 0.979 | 0.979 | 0.979 |
| Snare | 45 | 33 | 32 | 1 | 13 | 0.970 | 0.711 | 0.821 |
| Hi-hat | 0 | 3 | 0 | 3 | 0 | 0.000 | n/a | 0.000 |
| Toms | 30 | 16 | 16 | 0 | 14 | 1.000 | 0.533 | 0.696 |
| Cymbals | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| Other percussion | 32 | 0 | 0 | 0 | 32 | n/a | 0.000 | 0.000 |

All 99 emitted hits remain close to a real annotated onset within 50 ms. The expanded physical-feature classifier recognizes toms and sharply reduces snare/hi-hat confusion while retaining a conservative onset gate. Recall is still limited: this recording's tambourine often lands within milliseconds of a snare, and the research path does not recover those 32 separate annotations.

The notation gain comes from two corrections: beat tracking now analyzes the full mix rather than the sparse drum stem, and the complete observed piecewise beat map plus bar-one offset reaches quantization instead of being flattened to one BPM. Automatic drafts favor readable quarter/eighth/sixteenth and eighth-triplet grids; the editor still permits finer manual snapping.

## Cross-style regression

The same conservative detector was also evaluated against all 23 MDB Drums isolated reference stems (7,994 annotations) without changing the number of onset candidates:

| Metric | Baseline | Accuracy pass |
| --- | ---: | ---: |
| Aggregate class precision | 0.647 | **0.804** |
| Aggregate class recall | 0.387 | **0.480** |
| Aggregate class F1 | 0.484 | **0.601** |

This is a breadth regression over rock, pop, metal, country, reggae, and multiple jazz styles. It is not an independent unseen test set: the corpus was inspected while designing the deterministic feature rules, so these numbers must not be presented as a production model generalization claim.

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
4. Ran the durable normalization, fine-tuned Demucs isolation, spectral transcription, full-mix beat tracking, piecewise quantization, and score-generation pipeline.
5. Opened the rendered drum editor and verified 99 notation events.
6. Downloaded the private isolated drum stem.
7. Generated and signature-checked MIDI, MusicXML, and PDF exports.
8. Captured the rendered editor and stored the generated events for scoring.
9. Soft-deleted the project and verified that every signed artifact URL was revoked.

The updated automated browser journey passed in 3.5 minutes.

Baseline artifacts are under `data/benchmark-mdb-beatles/output/`; updated artifacts are under `data/benchmark-mdb-beatles/output-v2/`. Both are local and Git-ignored. Each directory contains the machine-readable score, rendered editor, isolated stem, and all three exports.

## Scoring method

- Raw onset evaluation uses one-to-one matching with the standard 50 ms window, plus a stricter 20 ms view.
- Class-aware scoring maps DrumScribe's detailed instrument names to MDB's six top-level classes.
- Exact notation scoring maps each reference onset to the closest sixteenth-note slot using MDB's annotated beat grid, then requires the generated measure, beat slot, and class to match exactly.
- Source separation uses scale-invariant SDR and waveform correlation against the isolated reference drum recording after mono conversion and length alignment.
- Hashes of both references and predictions are saved with the JSON result so the run is auditable.

## Engineering decision

Do not treat the improved local research path as production transcription quality. It remains behind the existing production safety gate because the Demucs weight/training-data rights are not cleared for the commercial deployment and the deterministic classifier still has material recall gaps.

The next model iteration should be accepted only after it:

1. Recovers layered/near-simultaneous events rather than selecting one class per broadband onset.
2. Distinguishes open/closed/pedal hi-hat, ride/crash, and side-stick/tambourine from licensed model output.
3. Adds downbeat inference for songs whose first detected pulse is not bar one.
4. Clears a commercial transcription/separation provider contract or replaces research weights with fully documented commercially licensed weights.
5. Passes a separately held-out, rights-cleared evaluation set with predeclared release thresholds.

## Reproduction

The browser harness is `apps/web/e2e/benchmark-mdb.spec.ts`. The deterministic scorer is `scripts/score_drum_benchmark.py`. Both are opt-in and require locally downloaded, rights-cleared benchmark data.
