# DrumScribe model and data licensing register

Last reviewed: 2026-08-29. This is an engineering inventory, not legal advice.

DrumScribe is fail-closed: production may enable a provider only when its runtime
`ProviderLicense.status` is `commercial_allowed`. “Unresolved” means exactly that;
an open-source code license does not automatically settle checkpoint or training-data
rights. `require_production_safe()` rejects unresolved and non-commercial providers.

## Enabled components

| Component | Repository/project | Code license | Weights | Training data | Commercial use | Attribution / restrictions | Decision |
|---|---|---|---|---|---|---|---|
| DrumScribe spectral research provider | This repository | Project code | None | None | Not production-enabled | Preserve notices for optional NumPy/SciPy/librosa dependencies | Local development and benchmarking only; heuristics are not represented as a trained AI model |
| DrumScribe mock providers | This repository | Project code | None | Synthetic only | Yes, as test infrastructure | Must never be described as real transcription or separation | Tests and deterministic local workflows |
| Future commercial transcription adapter | No vendor selected | Contract-dependent | Contract-dependent | Contract-dependent | No, until a signed commercial right and DPA are recorded | Record contract reference, retention, regions, subprocessors, and model-improvement terms | Configuration refuses activation without explicit confirmation; no network adapter is shipped |

## Evaluated research/source-separation components

| Component | Repository/project | Code license | Weights license | Training-data license | Commercial use allowed? | Attribution / distribution restrictions | Decision |
|---|---|---|---|---|---|---|---|
| Demucs v4 / `htdemucs` | [facebookresearch/demucs](https://github.com/facebookresearch/demucs) (archived) | MIT for repository code | Not clearly granted by the repository license; model-specific permission remains unresolved | README states MUSDB plus 800 additional songs; rights for the additional corpus are not documented for our purpose | **Unresolved** | MIT notice for code; do not bundle/download weights in production until written clearance identifies the exact checkpoint | Optional isolated local adapter only; production gate rejects it |
| ADTOF | [MZehren/ADTOF](https://github.com/MZehren/ADTOF) | CC BY-NC-SA 4.0 for repository content | Covered only by the non-commercial repository terms unless separately licensed | Crowdsourced/source-specific; dataset access and downstream rights require separate review | **No** under current terms | Attribution, non-commercial, ShareAlike; do not redistribute or serve commercially | Excluded from production; research evaluation only if its conditions are met |
| LarsNet checkpoints | [polimi-ispl/larsnet](https://github.com/polimi-ispl/larsnet) | No clear root code-license grant located in the reviewed repository | CC BY-NC 4.0 per project README | StemGMD is described as CC BY 4.0, but checkpoint terms remain non-commercial | **No** for pretrained checkpoints | Attribution and non-commercial restriction; code itself also needs a clear grant | Excluded from production |
| Omnizart | [MCT Lab/omnizart](https://github.com/Music-and-Culture-Technology-Lab/omnizart) | MIT for repository code | Checkpoint license not separately clear in reviewed project materials | Drum checkpoint training-data provenance/terms not fully resolved here | **Unresolved** | Do not assume MIT code terms cover downloaded checkpoints or datasets | Not integrated; require checkpoint, data, and dependency review first |

## Libraries and tools

| Component | License | Model/data concern | Decision |
|---|---|---|---|
| FFmpeg / FFprobe | Build-dependent LGPL/GPL configuration | No model | Runtime executable only; production image must record exact build/configuration and notices |
| NumPy | BSD-3-Clause | No model | Optional research dependency; retain notices |
| SciPy | BSD-3-Clause | No model | Optional research dependency; retain notices |
| librosa | ISC | No model | Optional research dependency; retain notices |
| ReportLab | BSD | No model | Optional PDF dependency; engine also includes a dependency-free PDF fallback |

## Candidate proprietary-training data

| Dataset | Source | License | Commercial training assessment | Requirements / decision |
|---|---|---|---|---|
| Expanded Groove MIDI Dataset v1.0.0 (E-GMD) | [Official Google dataset page](https://magenta.withgoogle.com/datasets/e-gmd) | CC BY 4.0 | Candidate is compatible with commercial use, subject to counsel confirming the planned model/distribution treatment | Record version and official archive SHA-256, preserve Google attribution and paper citation, identify dataset use in model card, and keep split groups leakage-safe. Never auto-download its 90 GB archive |
| Customer uploads/corrections | DrumScribe users | User content; no training grant by default | **No** | Never train on uploads or edits without a separate, explicit opt-in and documented lawful basis |
| Third-party accompaniment | Not selected | Not selected | **No** | Do not create mixed augmentations until every accompaniment recording has compatible commercial ML rights and attribution metadata |

## Production-release gate

Before changing any provider to `commercial_allowed`, record all of the following in
this file and in the deploy configuration:

1. Exact code version/hash and SPDX license.
2. Exact checkpoint hash, its license grant, and redistribution/hosted-inference terms.
3. Training datasets and licenses, including attribution and opt-out obligations.
4. Every material dependency and the production image’s FFmpeg license configuration.
5. Written legal/product approval, contract reference where applicable, regions,
   retention, subprocessors, and whether customer audio may be used for provider training.

No current automatic drum transcription or source-separation model is approved by
this register for commercial production. The deterministic mock can exercise the
pipeline, and the spectral heuristic can support local research, but neither should
be used to make a production-quality transcription claim.

