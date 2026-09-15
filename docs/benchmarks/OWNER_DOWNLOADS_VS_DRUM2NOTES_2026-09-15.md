# Owner-download real-song comparison — 15 September 2026

## Decision

This run does **not** establish accuracy for the four downloads. No trustworthy,
time-aligned drum annotation for the exact audio bytes was available. It is a
same-audio product-output comparison and stress test. Model confidence and
inter-system agreement must not be advertised as accuracy.

For launch accuracy, the current reproducible evidence remains the annotated
100-excerpt real-song suite: DrumToScore v6 scored **78.72% micro F1 at 50 ms**
versus **71.39%** for Drum2Notes and won 85/100 excerpts. That suite is an opened
development benchmark, not an independent certification or a 90% claim. See
`REAL_SONG_100_V6_VS_DRUM2NOTES.md`.

## Method

- Inputs: the owner-supplied Tajdar-E-Haram file and the three most recently
  downloaded additional audio files available at test time.
- Window: the loudest 20-second RMS window from each file.
- Fairness: both products received the exact same 44.1 kHz stereo PCM WAV bytes.
- DrumToScore: `htdemucs_ft` isolation followed by
  `drumscribe-recall-fusion-v6`, executed locally on Apple MPS.
- Competitor: Klangio Drum2Notes public 20-second demo and its audio-aligned
  MusicJSON result.
- Comparison taxonomy: kick, snare, hi-hat, tom and cymbal; one-to-one event
  matching within 50 ms.
- Independent diagnostic: a generic onset detector was run on the isolated drum
  stem. Its count is useful for spotting silence or severe under-detection, but
  is not an annotation and is not used as an accuracy score.

## Results

| Recording | Window start | DrumToScore events | Drum2Notes events | DrumToScore mean confidence | 50 ms agreement F1 | Stem onset diagnostic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tajdar-E-Haram (Atif Aslam / Coke Studio 8 file) | 565 s | 15 | 144 | 21.61% | 10.06% | 108 |
| If I Could Fly | 30 s | 128 | 157 | 57.25% | 87.72% | 59 |
| BAILAOK | 75 s | 0 | 18 | 0.00% | 0.00% | 32 at near-silent RMS 0.004 |
| LEDGNEDS FROM THE CELTIC ISLES MVMT 3 | 65 s | 66 | 102 | 39.74% | 40.48% | 92 |

Aggregate agreement was 53.02% F1. That number is not a winner score: agreement
can be high when both products make the same mistake and low when either product
is correct. The useful findings are:

- The two systems are closely aligned on `If I Could Fly`.
- DrumToScore deliberately returned no hits on the near-silent separated
  `BAILAOK` window while Drum2Notes returned 18. This may be correct rejection,
  but only a human reference can confirm it.
- Tajdar-E-Haram is a clear supported-taxonomy risk. The low confidence and
  15-versus-144 count gap show that tabla/qawwali percussion is outside the
  product's currently defensible western-drum-kit performance envelope.
- The Celtic recording also shows probable recall risk relative to both the
  competitor and the independent onset diagnostic.

## Launch implication

DrumToScore is suitable for a carefully labeled beta focused on western drum-kit
music, with editable output and no blanket accuracy claim. It is not ready to be
marketed as 90% accurate for every genre or for tabla/qawwali percussion. The UI
and marketing should continue to call low-confidence output an editable draft,
and unsupported percussion should be disclosed until an annotated evaluation and
model work cover those instruments.

## Reproduction and evidence

Run:

```sh
.research-models/adtof-env/bin/python \
  scripts/run_unreferenced_song_comparison.py \
  "/path/to/Tajdar-E-Haram.mp3" \
  "/path/to/If I Could Fly.mp3" \
  "/path/to/BAILAOK.mp3" \
  "/path/to/LEDGNEDS FROM THE CELTIC ISLES MVMT 3.mp3" \
  --device mps
```

Machine-readable results, source hashes, selected windows, raw DrumToScore hits,
and raw Drum2Notes responses are retained locally under
`output/owner-download-comparison-2026-09-15/`. Copyrighted source audio and
derived clips/stems are local evidence only and must not be committed or
redistributed.
