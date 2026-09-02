# Supported-kit hybrid v1

Date completed: 2026-09-02

Decision: **the frozen DrumScribe hybrid exceeded the existing Drum2Notes
comparison target on a new ten-track holdout.** Its strict six-family micro F1
was **78.13% at 20 ms**, versus the earlier Drum2Notes result of **74.64%**, a
gain of **3.48 percentage points**. This is a supported-kit synthetic hard-metal
result, not evidence of 90% accuracy on arbitrary released music.

## What changed

The error audit showed that the two existing first-party model families were
complementary:

- `groove-stacked-articulation-v16` is retained for the continuous cymbal and
  hi-hat families.
- `supported-kit-oaf-v24` is used for kick, snare, tambourine and tom families.
- A checkpoint-pinned decoder applies class-specific sub-frame timing offsets
  learned from the previously opened `ashes-opened-demucs-dev` recording.
- The external runner verifies the decoder/checkpoint hash relationship and
  writes the existing bounded, atomic JSON provider contract.

The family policy and decoder were frozen before the new holdout was generated.
Prediction read the isolated stems but did not read any holdout reference file.

## Fresh holdout result

| Metric | DrumScribe hybrid | Comparison target |
| --- | ---: | ---: |
| Six-family micro F1, 20 ms | **78.13%** | 74.64% |
| Six-family macro F1, 20 ms | 75.23% | — |
| Precision, 20 ms | 91.18% | — |
| Recall, 20 ms | 68.34% | — |
| Six-family micro F1, 50 ms | 80.85% | — |
| Mean matched timing error, 20 ms | 8.01 ms | — |

The ten deterministic tracks cover thrash, nu metal, metalcore, death metal,
doom, groove metal, industrial metal, progressive metal, power metal and
hardcore. They contain 2,391 labeled events and use different titles, tempos and
seeds from the earlier ten-track suite.

| Family | Precision | Recall | F1 at 20 ms |
| --- | ---: | ---: | ---: |
| Kick | 96.95% | 91.87% | 94.34% |
| Snare | 88.85% | 85.56% | 87.17% |
| Tom | 84.09% | 77.08% | 80.43% |
| Tambourine | 72.50% | 72.50% | 72.50% |
| Cymbal | 80.21% | 53.19% | 63.97% |
| Hi-hat | 87.92% | 37.89% | 52.96% |

The largest remaining problem is hi-hat recall. The next meaningful model work
is a diverse, commercially cleared separated-stem corpus with dense hi-hat and
cymbal articulation labels, followed by a genuinely independent commercial-mix
test set.

## Reproduction

Generate the sealed suite:

```bash
uv run --project ml python scripts/run_supported_kit_hybrid_benchmark.py generate \
  --output output/supported-kit-hybrid-holdout-v1-2026-09-02
```

Separate the uniquely named inputs with `htdemucs_ft`, then predict without
opening references:

```bash
uv run --project ml --extra train python \
  scripts/run_supported_kit_hybrid_benchmark.py predict \
  --output output/supported-kit-hybrid-holdout-v1-2026-09-02 \
  --demucs-root output/supported-kit-hybrid-holdout-v1-2026-09-02/demucs-unique \
  --repository . --device mps
```

Score only after prediction artifacts are frozen:

```bash
uv run --project ml python scripts/run_supported_kit_hybrid_benchmark.py score \
  --output output/supported-kit-hybrid-holdout-v1-2026-09-02
```

The durable result is
`output/supported-kit-hybrid-holdout-v1-2026-09-02/benchmark-result.json`.

## Release boundary

The provider is application-integrated as an explicit research beta and remains
fail-closed in production. The result does not clear the general-song accuracy
gate, and the repository still lacks final attribution/model-card approval for
all component weights and commercially approved rights for the `htdemucs_ft`
checkpoint and training provenance.
