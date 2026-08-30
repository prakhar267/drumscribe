# MDB Drums benchmark: MusicDelta_Beatles

Date: 2026-08-30

Application revision: `6995d3e` plus the benchmark harness introduced with this report

Runtime: `demucs-isolated-v4` (`htdemucs`) + `research-spectral-v1` + `research-librosa-beat-v1`

## Result

**DrumScribe did not produce an exact match to the reference drum notation.**

The current research pipeline is useful for a first timing draft, especially for kick drum, but it is not accurate enough to claim faithful multi-instrument drum transcription or release-quality notation.

| Metric | Result |
| --- | ---: |
| Reference events | 154 |
| DrumScribe events | 102 |
| Class-aware precision / recall / F1 at 50 ms | 0.667 / 0.442 / 0.531 |
| Class-aware precision / recall / F1 at 20 ms | 0.569 / 0.377 / 0.453 |
| Onset-only precision / recall / F1 at 50 ms | 1.000 / 0.662 / 0.797 |
| Exact notated class+slot precision / recall / F1 | 0.069 / 0.045 / 0.055 |
| Exact notated slot-only precision / recall / F1 | 0.373 / 0.247 / 0.297 |
| Reference / generated tempo | 111.11 / 112.35 BPM |
| Absolute tempo error | 1.24 BPM |
| Drum-stem SI-SDR | -2.02 dB |
| Drum-stem waveform correlation | 0.621 |

### Instrument results at 50 ms

| MDB class | Reference | Predicted | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Kick | 47 | 47 | 46 | 1 | 1 | 0.979 | 0.979 | 0.979 |
| Snare | 45 | 38 | 22 | 16 | 23 | 0.579 | 0.489 | 0.530 |
| Hi-hat | 0 | 17 | 0 | 17 | 0 | 0.000 | n/a | 0.000 |
| Toms | 30 | 0 | 0 | 0 | 30 | n/a | 0.000 | 0.000 |
| Cymbals | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| Other percussion | 32 | 0 | 0 | 0 | 32 | n/a | 0.000 | 0.000 |

The onset-only score shows that all 102 generated hits were close to a real annotated onset within 50 ms. The larger class-aware error comes from instrument identification: this research provider only emits kick, snare, or closed hi-hat, while the reference contains toms and other percussion. The low exact-notation score also exposes accumulated beat-grid drift from forcing a naturally performed excerpt onto one constant tempo.

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
4. Ran the durable normalization, Demucs isolation, spectral transcription, beat tracking, quantization, and score-generation pipeline.
5. Opened the rendered drum editor and verified 102 notation events.
6. Downloaded the private isolated drum stem.
7. Generated and signature-checked MIDI, MusicXML, and PDF exports.
8. Captured the rendered editor and stored the generated events for scoring.
9. Soft-deleted the project and verified that every signed artifact URL was revoked.

The automated browser journey passed in 2.6 minutes.

Generated artifacts are retained locally under `data/benchmark-mdb-beatles/output/` and are not committed. The machine-readable score is `benchmark-results.json`; the captured user view is `drumscribe-editor.png`.

## Scoring method

- Raw onset evaluation uses one-to-one matching with the standard 50 ms window, plus a stricter 20 ms view.
- Class-aware scoring maps DrumScribe's detailed instrument names to MDB's six top-level classes.
- Exact notation scoring maps each reference onset to the closest sixteenth-note slot using MDB's annotated beat grid, then requires the generated measure, beat slot, and class to match exactly.
- Source separation uses scale-invariant SDR and waveform correlation against the isolated reference drum recording after mono conversion and length alignment.
- Hashes of both references and predictions are saved with the JSON result so the run is auditable.

## Engineering decision

Do not treat the current local research path as production transcription quality. Keep it behind the existing production safety gate.

The next model iteration should be accepted only after it:

1. Emits all supported drum classes, including toms, cymbals, hi-hat states, and other-percussion handling.
2. Adds downbeat-aware, variable-tempo tracking instead of one global BPM.
3. Improves snare classification and reduces tom/percussion-to-hi-hat confusion.
4. Improves drum isolation against true stems.
5. Re-runs this harness over the full 23-track MDB Drums set, with predeclared release thresholds rather than tuning against this single excerpt.

## Reproduction

The browser harness is `apps/web/e2e/benchmark-mdb.spec.ts`. The deterministic scorer is `scripts/score_drum_benchmark.py`. Both are opt-in and require locally downloaded, rights-cleared benchmark data.
