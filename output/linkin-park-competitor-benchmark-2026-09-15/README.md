# Linkin Park “In the End” competitor probe

Date: 2026-09-15

Audio fingerprint: `15f6579096803361f77f82026273d4ec59f0938457b0e71827a12d2786a4aaf2`

Audio duration: 216.398333 seconds

## Reference

- Songsterr drum part 9, revision 8352935: <https://www.songsterr.com/a/wsa/linkin-park-in-the-end-drum-tab-s385697t9/r8352935>
- Independent drum-sheet PDF: <https://danielbatera.com.br/newsite/wp-content/uploads/2012/06/patitura-bateria-linkin-park-in-the-end-portal-daniel-batera-drum-sheet.pdf>
- Reference tempo: 105 BPM.
- The uploaded recording's first main drum onset is 19.2059 seconds. This offset was measured from the audio and applied to the reference pattern.

The uploaded instrumental is not proven to be the identical master/mix used by the notation sources. Songsterr is community-authored notation rather than contractual ground truth. Results are therefore an engineering estimate, not a certified accuracy claim.

## Identical free 20-second probe

Drum2Notes exposes only the first 20 seconds in its free demo. In this recording the drums begin at about 19.21 seconds, leaving only six reference events in the common window. The sample is too small to generalize to whole-song quality.

Drum2Notes result: <https://drum2notes.klang.io/en/file?id=d01ec4b7-698f-4ff6-8f1b-7a7f40278fc2>

All scores below use one-to-one, class-aware onset matching. Every matched event was within 30 ms, so the 30, 50, and 100 ms scores are identical for this tiny window.

| System | Predicted events | TP | FP | FN | Precision | Recall | Micro F1 | Tempo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Drum2Notes | 8 | 5 | 3 | 1 | 62.50% | 83.33% | 71.43% | 103 BPM |
| DrumToScore | 12 | 5 | 7 | 1 | 41.67% | 83.33% | 55.56% | 120 BPM |

Drum2Notes wins this limited probe. Both systems found five of the six reference hits; DrumToScore produced four more false positives. Drum2Notes' tempo error was 2 BPM, while DrumToScore's was 15 BPM.

## DrumToScore full-song result

Against the full Songsterr transcription previously extracted for this same project:

| Timing tolerance | Precision | Recall | Micro F1 |
|---|---:|---:|---:|
| 30 ms | — | — | 46.38% |
| 50 ms | 64.98% | 70.05% | 67.42% |
| 100 ms | 86.33% | 93.07% | 89.58% |

Family F1 at 50 ms: kick 73.72%, hi-hat 66.45%, cymbal 63.16%, snare 63.13%, and tom 38.71%.

Drum2Notes does not expose a full-song result without payment, so no honest full-song head-to-head number is available from its free tier.

## Second competitor

The same full 216.4-second file was submitted to <https://www.drumtranscription.com/> using its no-card free workflow. Its site says results are delivered by email as PDF, MIDI, and MusicXML. No result email had arrived after repeated checks during this run; score it only after structured output is received.

No payment method was entered or used for any competitor test.
