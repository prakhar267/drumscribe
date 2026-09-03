# Soft-song holdout v1

Date completed: 2026-09-02

## 2026-09-03 post-opened regression repair

The rhythm-completion fail-open bug is fixed: when no repeated texture is
proved, detected texture hits are retained, and expressive off-grid hits are no
longer silently discarded. The unchanged first-party hybrid therefore rises
from 51.85% to **56.30% family F1 at 20 ms** on this already opened song.

A research-only diagnostic using ADTOF after the existing separated stem plus
the repaired completion stage reaches **97.33% family micro F1 at 20 ms**
(97.85% precision, 96.81% recall, 96.98% macro F1). This is not a new holdout,
and ADTOF's current non-commercial terms prohibit using that stack for a paid
launch. See `docs/benchmarks/REAL_PERFORMANCE_RESEARCH_V1.md` for the independent
real-performance result and release decision.

Decision: **the unchanged hybrid does not generalize to this quiet soft-pop mix
at the hard-metal benchmark level.** On the sealed original song “Quiet
Horizon,” it reached **51.85% six-family micro F1 at 20 ms** and **56.30% at
50 ms**. Precision remained high, but low recall exposed a quiet-dynamics and
separation weakness.

## Test design

- One new original 84 BPM soft-pop/ballad arrangement, 20 seconds long.
- Ninety-four frozen drum events rendered with the CC BY 4.0 MuldjordKit.
- Code-generated mellow pad and bass backing; no third-party song recording.
- The `drumscribe-hybrid-v1` policy and decoder were unchanged after the prior
  hard-metal holdout.
- The primary full-mix prediction was completed and hashed before the reference
  was opened for scoring.

## Primary full-mix result

| Metric | Result |
| --- | ---: |
| Six-family micro F1, 20 ms | **51.85%** |
| Six-family macro F1, 20 ms | 41.59% |
| Precision, 20 ms | 85.37% |
| Recall, 20 ms | 37.23% |
| Six-family micro F1, 50 ms | 56.30% |
| Reference events | 94 |
| Predicted events | 41 |

| Family | F1 at 20 ms |
| --- | ---: |
| Kick | 100.00% |
| Cymbal | 48.00% |
| Hi-hat | 32.65% |
| Snare | 27.27% |
| Tom | 0.00% |

## Post-score diagnostic

The same unchanged model was run on the clean reference drum stem after the
primary result was frozen. This is a diagnostic, not a replacement score.

| Input | F1 at 20 ms | Precision | Recall | Predicted events |
| --- | ---: | ---: | ---: | ---: |
| Full mix → `htdemucs_ft` stem | 51.85% | 85.37% | 37.23% | 41 |
| Clean drum stem | **75.95%** | 93.75% | 63.83% | 64 |

The 24.10-point difference shows that quiet-event loss during separation is the
largest immediate problem. The detector still misses many soft hi-hats on the
clean stem, so both separation-aware training and low-dynamic hit training are
required. No thresholds, routing rules, offsets, or weights were changed after
this result.

## Artifacts

- Primary result:
  `output/soft-song-holdout-v1-2026-09-02/benchmark-result.json`
- Clean-stem diagnostic:
  `output/soft-song-holdout-v1-2026-09-02/clean-stem-diagnostic.json`
- Test audio:
  `output/soft-song-holdout-v1-2026-09-02/quiet-horizon-soft-ballad.wav`
- Reference notation:
  `output/soft-song-holdout-v1-2026-09-02/reference.pdf`

This single synthetic song is a regression probe, not a general accuracy
estimate for soft commercial recordings. It fails the earlier 74.64% comparison
target and therefore prevents any claim that the hybrid benchmark improvement
applies across genres or mix dynamics.
