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

## Standardized DrumToScore full-song result

The full-song score was rerun with the same audio alignment later used for every
competitor (`audio_time = -0.3498714285 + 0.9992 × score_time`). This supersedes
the earlier unaligned 46.38%/67.42%/89.58% comparison recorded during the first
probe.

| Timing tolerance | Precision | Recall | Micro F1 |
|---|---:|---:|---:|
| 30 ms | 85.73% | 92.50% | 88.98% |
| 50 ms | 86.18% | 92.98% | **89.45%** |
| 100 ms | 86.18% | 92.98% | 89.45% |

Family F1 at 50 ms: kick 94.25%, hi-hat 89.13%, snare 85.65%, cymbal 80.52%,
and tom 77.42%.

Drum2Notes does not expose a full-song result without payment, so no honest full-song head-to-head number is available from its free tier.

## Second competitor

The same full 216.4-second file was submitted to <https://www.drumtranscription.com/> using its no-card free workflow. Its site says results are delivered by email as PDF, MIDI, and MusicXML. No result email had arrived after repeated checks during this run; score it only after structured output is received.

## Third competitor: Music Demixer

The same source file was uploaded to <https://musicdemixer.com/>. Its no-card free preview selected audio seconds **95–125** and returned original-timing drum MIDI, beat-aligned drum MIDI, PDF, and MusicXML.

For the event comparison, the Songsterr part was aligned once to the uploaded audio (`audio_time = -0.3498714285 + 0.9992 × score_time`) using the measured first main drum onset and an audio-onset timing fit. Both systems were then scored on exactly the competitor-selected 30-second window with one-to-one, five-family onset matching.

| System | Predicted events | Reference events | TP | FP | FN | Precision | Recall | Micro F1 @ 50 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DrumToScore | 202 | 196 | 180 | 22 | 16 | 89.11% | 91.84% | **90.45%** |
| Music Demixer | 297 | 196 | 193 | 104 | 3 | 64.98% | 98.47% | **78.30%** |

Family F1 at 50 ms:

| System | Kick | Snare | Hi-hat | Toms | Cymbals |
|---|---:|---:|---:|---:|---:|
| DrumToScore | 92.44% | 89.36% | 92.59% | 66.67% | 70.59% |
| Music Demixer | 99.21% | 65.63% | 81.25% | 100.00% | 31.58% |

DrumToScore wins this 30-second comparison by **12.15 percentage points**. Music Demixer had excellent recall, but its 104 false positives—especially extra snares and cymbals—reduced precision. The tom and cymbal supports are only four and six reference events, respectively, so those family percentages are not stable whole-song estimates.

Music Demixer's beat-aligned export correctly identified **105 BPM**, but encoded the section in **3/4** instead of the reference **4/4**. DrumToScore's project tempo remained **120 BPM**, so DrumToScore won event placement while Music Demixer won tempo detection; neither result is perfect notation.

The free preview was consumed without entering or using a payment method. Its downloaded ZIP remains local and is not committed because it is derived from the user-supplied recording.

## Fourth competitor: DrumScript full song

[DrumScript v0.2.1](https://github.com/DrumScript/DrumScript/releases/tag/v0.2.1)
is an Apache-2.0 open-source command-line competitor. The exact v0.2.1 release
commit (`d1e1f744d29ff8564628aa45c238f2365bc5e0e3`) processed the complete
216.4-second file with its documented `--full-song` mode. It generated a
three-page PDF, MIDI, and JSON without an account, payment, or card.

Both systems were evaluated over the complete song against the same 1,026
Songsterr events, using the same alignment, five-family mapping, and one-to-one
class-aware onset matcher.

| System | Predicted events | TP | FP | FN | Precision | Recall | Micro F1 @ 50 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| DrumToScore | 1,107 | 954 | 153 | 72 | 86.18% | 92.98% | **89.45%** |
| DrumScript v0.2.1 | 1,174 | 365 | 809 | 661 | 31.09% | 35.58% | **33.18%** |

| System | 30 ms F1 | 50 ms F1 | 100 ms F1 | Tempo |
|---|---:|---:|---:|---:|
| DrumToScore | **88.98%** | **89.45%** | **89.45%** | 120 BPM project metadata |
| DrumScript v0.2.1 | 19.82% | 33.18% | 49.55% | 103.4 BPM detected |

Family F1 at 50 ms:

| System | Kick | Snare | Hi-hat | Toms | Cymbals |
|---|---:|---:|---:|---:|---:|
| DrumToScore | 94.25% | 85.65% | 89.13% | 77.42% | 80.52% |
| DrumScript v0.2.1 | 32.26% | 30.77% | 39.66% | 0.00% | 7.34% |

DrumToScore wins this full-song test by **56.27 percentage points** at 50 ms.
DrumScript exported no tom-class events, generated 809 false positives, and its
score-grid timing drifted because the detected 103.4 BPM was below the 105 BPM
reference. The DrumScript run took approximately 5 minutes 26 seconds on this
Mac (its Demucs stage reported 2.60 minutes).

The generated DrumScript PDF, MIDI, and JSON were copied to
`~/Downloads/DrumScript-Linkin-Park-full-song/` for manual inspection. They are
not committed because they are derived from the user-supplied recording.

## Excluded full-song candidate

[PineThink Score](https://pinethink.com/score/) processed the full song locally
without an account or card, but its Drums tab explicitly kept drums as practice
audio and did not convert the rhythm to notes. It is therefore a stem-separation
tool for this use case, not a valid drum-notation competitor, and was not scored.

No payment method was entered or used for any competitor test.
