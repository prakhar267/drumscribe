# 100-recording real-performance competitor benchmark

Date completed: 2026-09-03

Update, 2026-09-05: Klangio Drum2Notes has now been submitted on all 100
frozen inputs. DrumScribe reached 91.70% detailed F1 versus Drum2Notes at
67.83%; Drum2Notes returned usable output for 61/100 inputs. See
`docs/benchmarks/DRUM2NOTES_LIVE_100_BENCHMARK.md` for the complete protocol,
failure analysis and completed-only diagnostic.

## Result

DrumScribe processed all 100 selected recordings and reached **91.70% detailed
event micro F1 at ±50 ms**. The same files and references were run through the
open-source DrumScript alpha, which reached **54.45%**. DrumScribe's measured
lead on this exact test is **37.25 percentage points**.

This is a real-human-performance **drum detector** benchmark, not a 100-song
full-mixture benchmark. The inputs are isolated electronic-drum recordings from
the Google Magenta Groove MIDI Dataset (GMD), with aligned MIDI-derived ground
truth. It does not exercise source separation from vocals, guitars, or bass; it
does not score score-layout or notation-readability errors. The wider GMD test
split was also opened in earlier research. The result therefore cannot support
a claim that DrumScribe is 91.70% accurate on arbitrary commercial songs.

## Category results

The primary metric is class-aware, one-to-one event micro F1 at ±50 ms over 12
naturally supported detailed drum labels. Each category contributes exactly
25 recordings, or 25% of the test.

| Benchmark category | Recordings | Share | Reference hits | DrumScribe | DrumScript | DrumScribe lead |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Heavy rock + punk | 25 | 25% | 1,445 | **95.10%** | 43.40% | +51.70 pp |
| Pop + soul | 25 | 25% | 2,521 | **92.01%** | 73.33% | +18.67 pp |
| Funk + hip-hop | 25 | 25% | 3,098 | **90.89%** | 58.12% | +32.77 pp |
| Jazz + world | 25 | 25% | 1,524 | **89.52%** | 28.44% | +61.07 pp |
| **All categories** | **100** | **100%** | **8,588** | **91.70%** | **54.45%** | **+37.25 pp** |

This corpus has rock and punk performances but no `metal` label. “Heavy rock +
punk” must not be relabeled as a 25-song hard-metal result.

## Overall metrics

| Metric | DrumScribe v16 | DrumScript 0.2.1 |
| --- | ---: | ---: |
| Detailed event F1, ±20 ms | **90.83%** | 52.86% |
| Detailed event F1, ±50 ms | **91.70%** | 54.45% |
| Six-family event F1, ±20 ms | **91.42%** | 58.53% |
| Six-family event F1, ±50 ms | **92.31%** | 60.53% |
| Detailed precision, ±50 ms | **95.17%** | 59.72% |
| Detailed recall, ±50 ms | **88.47%** | 50.02% |
| Matched detailed onset MAE, ±50 ms | **5.06 ms** | 6.85 ms |

DrumScribe produced 7,984 events against 8,588 references. DrumScript produced
7,193. All 100 jobs completed successfully for both systems.

The weakest DrumScribe category is jazz/world at 89.52%. The weakest supported
detailed classes across the complete set are pedal hi-hat (69.74%), open
hi-hat (74.49%), ride bell (83.33%), crash (83.52%), and snare (88.92%). These
are the next accuracy targets; the current evidence does not show 90% in every
genre or every class.

## Five direct competitor products checked

“Top five” here means five direct, publicly discoverable drum-to-notation
alternatives, not an audited market-share ranking. No reliable public
market-share table exists for this niche.

| Competitor | Same 100 completed | What was verified | Why no 100-track score |
| --- | ---: | --- | --- |
| Klangio Drum2Notes | **100 submitted; 61 usable** | The live public demo was run on the frozen 100 inputs on 2026-09-05. It scored 67.83% detailed F1 at ±50 ms under the strict failure-inclusive protocol. | 39 short inputs returned service errors. See `DRUM2NOTES_LIVE_100_BENCHMARK.md`. |
| Drumscrib | 0 | Current beta accepts uploaded audio, says errors remain, and prices 10 transcriptions at €15. | 100 files require a €150 purchase before optional MIDI/MuseScore files. No payment was authorized. Its terms also restrict products to personal use. |
| PlayDrumsOnline | 0 | The free plan permits one transcription; private MP3 upload and unlimited AI sheets require a paid plan. | One free item cannot support a 100-record comparison, and no subscription purchase was authorized. |
| Drum AI | 0 | The transcription page loads, but the active browser session requires sign-in before a private upload. | No authenticated benchmark session or bulk evaluation interface was available. |
| DrumScript | **100** | Public Apache-2.0 alpha v0.2.1 at commit `59a912be8d5f9866798ead45930b9bf1fd8c9dab`. | Fully completed and scored above. |

Official sources: [Drum2Notes](https://drum2notes.klang.io/), [Klangio plan
limits](https://klang.io/help/compare-apps-and-subscriptions/), [Drumscrib
product/pricing](https://drumscrib.com/), [Drumscrib accuracy and beta
limitations](https://drumscrib.com/en/help), [Drumscrib
terms](https://drumscrib.com/en/terms_and_conditions), [PlayDrumsOnline upload
limits](https://www.playdrumsonline.com/create), [PlayDrumsOnline
pricing](https://www.playdrumsonline.com/premium), [Drum AI
transcription](https://www.drumai.me/transcription), and [DrumScript source and
alpha disclosure](https://github.com/DrumScript/DrumScript).

## Corpus and protocol

- Source: [Google Magenta Groove MIDI Dataset](https://magenta.tensorflow.org/datasets/groove),
  published under CC BY 4.0 with aligned human-performed audio and MIDI.
- Selection: 100 unique official-test recordings; 25 in each declared category.
- Exclusion: the ten audio hashes used in the earlier live Drum2Notes probe were
  excluded from this selection.
- Duration: first 20 seconds or the complete recording when shorter; 1,123.17
  seconds total (18 minutes 43.17 seconds).
- Reference: canonical MIDI-derived event onsets.
- Matching: class-aware, one-to-one onset matching at both ±20 ms and ±50 ms.
- Taxonomies: 12 naturally supported detailed labels, six instrument families,
  and core kick/snare/hi-hat.
- DrumScribe: frozen `groove-stacked-articulation-v16` configuration and seven
  hash-pinned checkpoints.
- DrumScript: unmodified public onset detector and standard polyphonic
  classifier. Rendering was skipped because it does not change detected event
  identity or timing.

## Reproduction

```bash
uv run --project ml --extra train python \
  scripts/run_100_track_genre_benchmark.py --device mps

git clone https://github.com/DrumScript/DrumScript \
  .research-models/drumscript
git -C .research-models/drumscript checkout \
  59a912be8d5f9866798ead45930b9bf1fd8c9dab
uv sync --project .research-models/drumscript --python 3.12
PYTHONPATH='ml/src:packages/music-engine/src:scripts' \
  .research-models/drumscript/.venv/bin/python \
  scripts/run_drumscript_100_track_benchmark.py --workers 4
```

Full local evidence is stored under
`output/100-track-genre-benchmark-2026-09-03/`. The committed compact evidence
is `docs/benchmarks/data/REAL_100_GENRE_COMPETITOR_BENCHMARK.json`.

## Integrity and claim boundary

- DrumScribe result SHA-256:
  `b763073b9255214703948b5018ed0b7d3e9be7ce09806039ff984d032f663cc5`
- DrumScript result SHA-256:
  `f2ec1a70f7aa7407b6beb4586c93b969d0e95e0ce58693e3006823fce39a4294`
- Both reports contain 100 unique input hashes, 100 raw prediction files, and
  the same 8,588 reference events.
- This benchmark supports the narrow statement “91.70% detailed event F1 on
  this 100-recording isolated GMD comparison.” It does **not** support “90% on
  all songs,” “90% end-to-end notation accuracy,” or a complete five-product
  leaderboard.
