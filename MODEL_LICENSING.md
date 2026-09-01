# DrumScribe model and data licensing register

Last reviewed: 2026-09-01. This is an engineering inventory, not legal advice.

DrumScribe is fail-closed: production may enable a provider only when its runtime
`ProviderLicense.status` is `commercial_allowed`. “Unresolved” means exactly that;
an open-source code license does not automatically settle checkpoint or training-data
rights. `require_production_safe()` rejects unresolved and non-commercial providers.

## Enabled components

| Component | Repository/project | Code license | Weights | Training data | Commercial use | Attribution / restrictions | Decision |
|---|---|---|---|---|---|---|---|
| DrumScribe spectral research provider | This repository | Project code | None | None | Not production-enabled | Preserve notices for optional NumPy/SciPy/librosa dependencies | Local development and benchmarking only; heuristics are not represented as a trained AI model |
| DrumScribe `kit-adaptive-corpus-v20` | This repository; SHA-256 `6ea37fb96531aac6d55f7909d527b02250b816fee56ecdc5851d9122d44badcf` | Project code | Clean-room checkpoint trained locally | Licensed Groove/E-GMD prepared corpus plus attributed FreePats-derived development material | Legally plausible subject to final attribution/model-card review; **accuracy gate failed** | Preserve dataset/sample attributions and exact training/benchmark lineage | Research runner only; do not select as production default or make a 90% claim |
| Beat This timing provider | [CPJKU/beat_this](https://github.com/CPJKU/beat_this) | MIT | `final0` checkpoint terms follow upstream distribution; separate grant not identified | Mixed research beat datasets; commercial treatment not fully audited | Not production-enabled | Preserve MIT attribution; do not infer training-data rights from code license | Local timing research; production gate rejects it |
| DrumScribe mock providers | This repository | Project code | None | Synthetic only | Yes, as test infrastructure | Must never be described as real transcription or separation | Tests and deterministic local workflows |
| AudioShake source-separation adapter | AudioShake Tasks API | Proprietary service | Provider-hosted | Provider statement says licensed data; contract controls | No, until account contract/DPA approval is recorded | Record credits, retention, regions, subprocessors, output rights, and model-improvement terms | Adapter and mocked contract tests ship; production refuses missing key/contract/approval |
| Music AI source-separation adapter | Music AI workflow API | Proprietary service | Provider-hosted | Contract-dependent | No, until exact workflow and contract/DPA approval are recorded | Record workflow slug/version, per-minute price, retention, subprocessors, output rights, and training use | Adapter and mocked contract tests ship; production refuses missing key/workflow/contract/approval |
| Klangio drum-transcription and beat adapters | Klangio Transcription API 0.2 | Proprietary service | Provider-hosted | Contract-dependent | No, until drum-model API access and commercial contract/DPA approval are recorded | Record API build/model, deletion date, regions, output rights, subprocessors, and training use | Current OpenAPI exposes `model=drums` and beat tracking; adapters and mocked contract tests ship; production refuses missing key/contract/approval |

## Evaluated research/source-separation components

| Component | Repository/project | Code license | Weights license | Training-data license | Commercial use allowed? | Attribution / distribution restrictions | Decision |
|---|---|---|---|---|---|---|---|
| Demucs v4 / `htdemucs` | [facebookresearch/demucs](https://github.com/facebookresearch/demucs) (archived) | MIT for repository code | Not clearly granted by the repository license; model-specific permission remains unresolved | README states MUSDB plus 800 additional songs; rights for the additional corpus are not documented for our purpose | **Unresolved** | MIT notice for code; do not bundle/download weights in production until written clearance identifies the exact checkpoint | Optional isolated local adapter only; production gate rejects it |
| YourMT3+ / YPTF.MoE+Multi | [mimbres/YourMT3](https://github.com/mimbres/YourMT3), [official demo source](https://huggingface.co/spaces/mimbres/YourMT3) | Conflicting upstream declarations: GitHub root GPL-3.0 while demo files/metadata state Apache-2.0 | No clear grant covering every checkpoint | Trained across mixed research datasets; commercial rights unresolved | **Unresolved** | Do not redistribute or deploy until code, checkpoint and every training source are reconciled | Process-isolated full-mix A/B provider only; production gate rejects it |
| OaF Drums | [Magenta Onsets and Frames](https://github.com/magenta/magenta/tree/main/magenta/models/onsets_frames_transcription) | Apache-2.0 | Official E-GMD checkpoint is distributed separately; exact checkpoint grant still requires review | E-GMD CC BY 4.0 | **Unresolved** for the downloaded checkpoint | Preserve Apache/CC BY notices and E-GMD citation; legacy TensorFlow environment stays isolated | Process-isolated stem A/B provider only; production gate rejects it |
| ADTOF | [MZehren/ADTOF](https://github.com/MZehren/ADTOF), [PyTorch port](https://github.com/xavriley/ADTOF-pytorch) | Upstream CC BY-NC-SA 4.0; PyTorch port has no declared repository license | Derived from the non-commercial upstream weights | Crowdsourced/source-specific; dataset access and downstream rights require separate review | **No** under current terms | Attribution, non-commercial, ShareAlike; the unlicensed port adds another distribution blocker | Explicitly excluded from production; local benchmark only |
| LarsNet checkpoints | [polimi-ispl/larsnet](https://github.com/polimi-ispl/larsnet) | No clear root code-license grant located in the reviewed repository | CC BY-NC 4.0 per project README | StemGMD is described as CC BY 4.0, but checkpoint terms remain non-commercial | **No** for pretrained checkpoints | Attribution and non-commercial restriction; code itself also needs a clear grant | Excluded from production |
| Omnizart | [MCT Lab/omnizart](https://github.com/Music-and-Culture-Technology-Lab/omnizart) | MIT for repository code | Checkpoint license not separately clear in reviewed project materials | Drum checkpoint training-data provenance/terms not fully resolved here | **Unresolved** | Do not assume MIT code terms cover downloaded checkpoints or datasets | Not integrated; require checkpoint, data, and dependency review first |
| Spotify Basic Pitch | [spotify/basic-pitch](https://github.com/spotify/basic-pitch) | Apache-2.0 repository | Distributed upstream model; exact artifact terms must still be recorded before bundling | Pitched-instrument AMT sources, not a drum-articulation corpus | **Not applicable to drum classification** | Preserve Apache notices if used for pitched-note features | Rejected as DrumScribe's detector: it is best suited to one pitched instrument at a time and has no 14-class drum head |
| ADT-STR | [pier-maker92/ADT_STR](https://github.com/pier-maker92/ADT_STR) | No root license located in the reviewed repository | No released checkpoint located | Paper uses curated one-shots plus rendered sequences; every source still needs a commercial-rights audit | **Unresolved** | Do not copy code or ship weights without an explicit grant | Architecture research only: diverse one-shot curation and sequence decoding informed the clean-room plan |
| Noise-to-Notes | [paper](https://arxiv.org/abs/2509.21739) | No public implementation located | No public checkpoint located | Paper combines drum datasets with MERT representations | **No deployable artifact** | The official MERT-v1-95M checkpoint is CC BY-NC 4.0 | Research reference only; its multi-feature fusion results cannot be reproduced or production-shipped from the paper alone |
| Separate-and-Detect | [ddman1101/Separate-and-detect](https://github.com/ddman1101/Separate-and-detect) | MIT repository code | Upstream checkpoint available; artifact/data grants require separate verification | Five broad drum classes across research datasets | **Unresolved** for checkpoint deployment | Preserve MIT notice; audit checkpoint and every dataset before use | Not adopted: reported mean MDB/ENST F1 is well below the 14-class 90% target |
| DrumSep / MDX23C | [openmirlab/mdxnet-infer](https://github.com/openmirlab/mdxnet-infer) | MIT repository code | No explicit weight license identified | Model-training corpus rights are not fully documented for this use | **Unresolved** | Do not bundle the six-stem checkpoint until its exact grant is obtained | Research-only possible source-separation baseline; not production-enabled |

## Libraries and tools

| Component | License | Model/data concern | Decision |
|---|---|---|---|
| FFmpeg / FFprobe | Build-dependent LGPL/GPL configuration | No model | Runtime executable only; production image must record exact build/configuration and notices |
| NumPy | BSD-3-Clause | No model | Optional research dependency; retain notices |
| PyTorch | BSD-3-Clause | No bundled weights | Optional training-only dependency; do not treat the framework license as approval for any checkpoint or dataset |
| SciPy | BSD-3-Clause | No model | Optional research dependency; retain notices |
| librosa | ISC | No model | Optional research dependency; retain notices |
| ReportLab | BSD | No model | Optional PDF dependency; engine also includes a dependency-free PDF fallback |

## Candidate proprietary-training data

| Dataset | Source | License | Commercial training assessment | Requirements / decision |
|---|---|---|---|---|
| Expanded Groove MIDI Dataset v1.0.0 (E-GMD) | [Official Google dataset page](https://magenta.withgoogle.com/datasets/e-gmd) | CC BY 4.0 | Candidate is compatible with commercial use, subject to counsel confirming the planned model/distribution treatment | Record version and official archive SHA-256, preserve Google attribution and paper citation, identify dataset use in model card, and keep split groups leakage-safe. Never auto-download its 90 GB archive |
| FreePats MuldjordKit 2020-10-18 | [FreePats acoustic drum kits](https://freepats.zenvoid.org/Percussion/acoustic-drum-kits.html) | CC BY 4.0 | Compatible with commercial augmentation subject to attribution | Use the committed one-shot catalog; credit “Drum samples provided by DrumGizmo.org.” plus recorded authorship; retain exact corpus hash |
| FreePats World Percussion 2020-09-05 | [FreePats world percussion](https://freepats.zenvoid.org/Percussion/world-percussion.html) | CC0 1.0 for samples | Compatible with commercial augmentation | Catalog currently uses the tambourine sample directory; preserve voluntary source credits and exact corpus hash |
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

No commercial provider is approved by this register yet because credentials,
account-specific product access, executed contracts/DPA, retention/training terms,
and a rights-cleared live benchmark have not been supplied. The implemented adapters
therefore remain fail-closed. The deterministic mock can exercise the pipeline, and
the spectral heuristic can support local research, but neither may be used to make a
production-quality transcription claim.

The repository's `drumscribe-events` CRNN architecture has no bundled checkpoint.
Any trained artifact starts as `NEEDS_LEGAL_REVIEW` and may become
`APPROVED_PRODUCTION` only after its exact dataset manifests, augmentation inputs,
Git/config provenance, model SHA-256, evaluation report and required attributions
pass the gate above.
