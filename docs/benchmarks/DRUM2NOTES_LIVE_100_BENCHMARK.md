# Drum2Notes live 100-recording comparison

Date completed: 2026-09-05

## Result

DrumScribe leads Klangio Drum2Notes on the unchanged 100-recording Groove
benchmark. The primary metric is detailed, class-aware event micro F1 with
one-to-one onset matching at ±50 ms.

| System | Completed transcriptions | Detailed precision | Detailed recall | Detailed F1 |
| --- | ---: | ---: | ---: | ---: |
| DrumScribe `groove-stacked-articulation-v16` | 100/100 | 95.17% | 88.47% | **91.70%** |
| Klangio Drum2Notes live public demo | 61/100 | 77.39% | 60.37% | **67.83%** |

DrumScribe's strict all-100 lead is **23.87 percentage points**. Drum2Notes
returned 61 usable MusicJSON transcriptions and 39 service errors. Failed items
remain in the frozen benchmark and are scored as zero predicted events; no
recording was replaced or removed.

## Category results

| Category | Recordings | DrumScribe | Drum2Notes | DrumScribe lead | Drum2Notes completed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Heavy rock + punk | 25 | **95.10%** | 53.31% | +41.79 pp | 13 |
| Pop + soul | 25 | **92.01%** | 83.54% | +8.47 pp | 18 |
| Funk + hip-hop | 25 | **90.89%** | 73.96% | +16.93 pp | 19 |
| Jazz + world | 25 | **89.52%** | 38.29% | +51.23 pp | 11 |
| **All categories** | **100** | **91.70%** | **67.83%** | **+23.87 pp** | **61** |

These are strict results over every preselected input. The genre labels are
benchmark groupings derived from the Groove dataset; “heavy rock + punk” is not
a hard-metal category.

## Completed-transcriptions-only diagnostic

For the 61 files on which Drum2Notes returned usable output, DrumScribe scored
**91.62%** and Drum2Notes scored **70.82%** detailed F1 at ±50 ms. DrumScribe's
lead remains **20.80 percentage points** after excluding the service failures.
This diagnostic is reported to separate recognition quality from input handling,
but it is not the primary all-100 result.

| Category | Completed files | DrumScribe | Drum2Notes |
| --- | ---: | ---: | ---: |
| Heavy rock + punk | 13 | **95.11%** | 57.63% |
| Pop + soul | 18 | **92.02%** | 85.41% |
| Funk + hip-hop | 19 | **90.87%** | 75.40% |
| Jazz + world | 11 | **89.13%** | 42.60% |

## Additional metrics

| Metric | DrumScribe | Drum2Notes |
| --- | ---: | ---: |
| Detailed F1, ±20 ms | **90.83%** | 44.78% |
| Detailed F1, ±50 ms | **91.70%** | 67.83% |
| Six-family F1, ±50 ms | **92.31%** | 79.40% |
| Core kick/snare/hi-hat F1, ±50 ms | **92.21%** | 79.60% |

## Service failures

All 100 uploads were accepted by the live endpoint. Drum2Notes subsequently
returned 37 `FileFormatException` failures and two empty-array processing
failures. Every failed input was shorter than 4.1 seconds; 34 of the 39 were
shorter than three seconds. DrumScribe processed all of these same files.

This behavior matters for an end-user product comparison, but it should not be
confused with note-recognition accuracy. That is why the completed-only
diagnostic is also reported above.

## Protocol

- Corpus: Google Magenta Groove MIDI Dataset, CC BY 4.0.
- Input: 100 isolated electronic-drum performances played by human drummers.
- Selection: the exact 100 hashes frozen in the 2026-09-03 benchmark; 25 items
  per category and no post-result substitution.
- Audio window: the first 20 seconds or the full recording when shorter;
  1,123.17 scored seconds in total.
- Reference: aligned, canonical MIDI-derived event onsets.
- Drum2Notes setting: `solo`, all drum notes, public free demo.
- Drum2Notes source: the audio-aligned MusicJSON consumed by its result viewer;
  no paid export was accessed.
- Matching: class-aware, one-to-one onset matching at ±20 ms and ±50 ms.

The run is reproducible and resumable with:

```bash
uv run --project ml python \
  scripts/run_drum2notes_100_track_benchmark.py --workers 3
```

The full local result is
`output/100-track-genre-benchmark-drum2notes-2026-09-05/benchmark-result.json`
with SHA-256
`ed94fee9ace8b3ca6f6c164e6849f98846da097066c1e2370f5aab4042a465d6`.
Compact committed evidence is in
`docs/benchmarks/data/DRUM2NOTES_LIVE_100_BENCHMARK.json`.

## Claim boundary

This supports the statement that DrumScribe outperformed the live Drum2Notes
demo on this exact 100-recording isolated-drum benchmark. It does **not** prove
that DrumScribe is more accurate on arbitrary commercial songs, source
separation, score engraving, or every drum kit. The test split was opened in
earlier research, and this repository is not an independent third-party audit.
