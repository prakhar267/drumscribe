# DrumScribe model and data licensing register

Last reviewed: 2026-09-06. This is an engineering inventory, not legal advice.

DrumScribe is fail-closed: production may enable a provider only when its runtime
`ProviderLicense.status` is `commercial_allowed`. “Unresolved” means exactly that;
an open-source code license does not automatically settle checkpoint or training-data
rights. `require_production_safe()` rejects unresolved and non-commercial providers.

## Enabled components

| Component | Repository/project | Code license | Weights | Training data | Commercial use | Attribution / restrictions | Decision |
|---|---|---|---|---|---|---|---|
| DrumScribe spectral research provider | This repository | Project code | None | None | Not production-enabled | Preserve notices for optional NumPy/SciPy/librosa dependencies | Local development and benchmarking only; heuristics are not represented as a trained AI model |
| DrumScribe `kit-adaptive-corpus-v20` | This repository; SHA-256 `6ea37fb96531aac6d55f7909d527b02250b816fee56ecdc5851d9122d44badcf` | Project code | Clean-room checkpoint trained locally | Licensed Groove/E-GMD prepared corpus plus attributed FreePats-derived development material | Legally plausible subject to final attribution/model-card review; **accuracy gate failed** | Preserve dataset/sample attributions and exact training/benchmark lineage | Research runner only; do not select as production default or make a 90% claim |
| DrumScribe `supported-kit-oaf-v24` | This repository; SHA-256 `5615181475f36b3bad0888977333db739b1ddae425579c53797c6a816f8fc027` | Project code | Clean-room checkpoint trained locally | Generated performances rendered with FreePats MuldjordKit samples (CC BY 4.0) | Legally plausible subject to final attribution/model-card review; **general-audio accuracy gate failed** | Credit MuldjordKit/DrumGizmo and FreePats; preserve corpus/checkpoint hashes and the synthetic-only scope | Supported-kit research only: 90.40% synthetic validation macro, but full-mix test micro F1 is 88.40%; not production-approved |
| DrumScribe `groove-multiview-articulation-v19-development` | This repository; config SHA-256 `da2263a26464207c3d98f16e2efa01f16a595faeca5b390e933bda3501756534` | Project code | First-party v18 stack plus focal specialist SHA-256 `fdb996c08cc7e24c164ec638397e3c9fa813f0014dff7ecad8e0b77a61211488` | Checkpoints use licensed Groove/E-GMD/FreePats material; decoder thresholds were calibrated on CC BY-NC 4.0 RWC annotations | **No** for this calibrated decoder; research only | Do not ship the RWC-calibrated rules; preserve model, config, partition, and evaluation hashes | Untouched 39-song research holdout improved from 50.25% to 62.80% detailed F1, but rare articulations remain unsupported and the 90% production gate failed |
| DrumScribe `rwc-temporal-stacker-v20-research` | This repository; config SHA-256 `8d98e1fb364cda1c8e2cbf3f9cfa1719b3086609735a189b8a192bbd983c7b5f`; checkpoint SHA-256 `b49d4dbe4b65300959e7b29b86a185f173d9ec886cd1c7dddbc5fd3d385dafc8` | Project code | First-party compact temporal stacker over the frozen v19 streams | Stacker weights, decoder and latency offsets were trained/calibrated on CC BY-NC 4.0 RWC annotations | **No**; research only | Do not ship the checkpoint or RWC-derived rules; the previous 39-song holdout is now secondary evidence | Five-fold first-50 OOF F1 is 60.45%; the fixed secondary-39 score is 63.08%; combined 89-song F1 is 61.53%, so the production/90% gate still fails |
| DrumScribe `drumscribe-recall-fusion-v3` | This repository; config SHA-256 `559158cb9f104a5b930787ef087eb5285bb02f837c14adf03f82512caa998c99` | Project code plus attributed ADTOF integration | First-party v18 stack plus the commercially authorized, hash-pinned ADTOF checkpoint | First-party checkpoints use Groove/E-GMD and rights-cleared samples; ADTOF model-use rights are covered by the separate owner grant | **Yes for DrumScribe** under `OWNER-ATTESTATION-2026-09-05` | Preserve upstream attributions; keep the ADTOF grant/checkpoint private; do not use MDB evaluation audio for training | Approved self-hosted production transcriber; 90.52% on the opened 11-track MDB same-audio benchmark, which is development evidence rather than a universal accuracy claim |
| Beat This timing provider | [CPJKU/beat_this](https://github.com/CPJKU/beat_this) | MIT | `final0`, SHA-256 recorded in the owner approval | Separately licensed for DrumScribe commercial inference | **Yes for DrumScribe** under `OWNER-ATTESTATION-2026-09-05` | Preserve MIT attribution; keep the separate grant private | Approved self-hosted timing provider |
| DrumScribe mock providers | This repository | Project code | None | Synthetic only | Yes, as test infrastructure | Must never be described as real transcription or separation | Tests and deterministic local workflows |
| AudioShake source-separation adapter | AudioShake Tasks API | Proprietary service | Provider-hosted | Provider statement says licensed data; contract controls | No, until account contract/DPA approval is recorded | Record credits, retention, regions, subprocessors, output rights, and model-improvement terms | Adapter and mocked contract tests ship; production refuses missing key/contract/approval |
| Music AI source-separation adapter | Music AI workflow API | Proprietary service | Provider-hosted | Contract-dependent | No, until exact workflow and contract/DPA approval are recorded | Record workflow slug/version, per-minute price, retention, subprocessors, output rights, and training use | Adapter and mocked contract tests ship; production refuses missing key/workflow/contract/approval |
| Klangio drum-transcription and beat adapters | Klangio Transcription API 0.2 | Proprietary service | Provider-hosted | Contract-dependent | No, until drum-model API access and commercial contract/DPA approval are recorded | Record API build/model, deletion date, regions, output rights, subprocessors, and training use | Current OpenAPI exposes `model=drums` and beat tracking; adapters and mocked contract tests ship; production refuses missing key/contract/approval |

## Evaluated research/source-separation components

| Component | Repository/project | Code license | Weights license | Training-data license | Commercial use allowed? | Attribution / distribution restrictions | Decision |
|---|---|---|---|---|---|---|---|
| Demucs v4 / `htdemucs_ft` | [facebookresearch/demucs](https://github.com/facebookresearch/demucs) (archived) | MIT for repository code | Four exact safetensors and bag hash are pinned in the owner approval | Separately licensed for DrumScribe commercial inference | **Yes for DrumScribe** under `OWNER-ATTESTATION-2026-09-05` | Preserve MIT attribution; do not represent the private grant as part of the public upstream license | Approved self-hosted production separator |
| YourMT3+ / YPTF.MoE+Multi | [mimbres/YourMT3](https://github.com/mimbres/YourMT3), [official demo source](https://huggingface.co/spaces/mimbres/YourMT3) | Conflicting upstream declarations: GitHub root GPL-3.0 while demo files/metadata state Apache-2.0 | No clear grant covering every checkpoint | Trained across mixed research datasets; commercial rights unresolved | **Unresolved** | Do not redistribute or deploy until code, checkpoint and every training source are reconciled | Process-isolated full-mix A/B provider only; production gate rejects it |
| OaF Drums | [Magenta Onsets and Frames](https://github.com/magenta/magenta/tree/main/magenta/models/onsets_frames_transcription) | Apache-2.0 | Official E-GMD checkpoint is distributed separately; exact checkpoint grant still requires review | E-GMD CC BY 4.0 | **Unresolved** for the downloaded checkpoint | Preserve Apache/CC BY notices and E-GMD citation; legacy TensorFlow environment stays isolated | Process-isolated stem A/B provider only; production gate rejects it |
| ADTOF | [MZehren/ADTOF](https://github.com/MZehren/ADTOF), [PyTorch port](https://github.com/xavriley/ADTOF-pytorch) | Public upstream ADTOF is CC BY-NC-SA 4.0; DrumScribe holds a separate commercial grant | Exact frame-RNN checkpoint SHA-256 is pinned in the owner approval | Separately licensed for DrumScribe commercial inference | **Yes for DrumScribe** under `OWNER-ATTESTATION-2026-09-05` | Preserve upstream attribution; keep weights private to DrumScribe infrastructure | Approved self-hosted production transcriber |
| LarsNet checkpoints | [polimi-ispl/larsnet](https://github.com/polimi-ispl/larsnet) | No clear root code-license grant located in the reviewed repository | CC BY-NC 4.0 per project README | StemGMD is described as CC BY 4.0, but checkpoint terms remain non-commercial | **No** for pretrained checkpoints | Attribution and non-commercial restriction; code itself also needs a clear grant | Excluded from production |
| Omnizart | [MCT Lab/omnizart](https://github.com/Music-and-Culture-Technology-Lab/omnizart) | MIT for repository code | Checkpoint license not separately clear in reviewed project materials | Drum checkpoint training-data provenance/terms not fully resolved here | **Unresolved** | Do not assume MIT code terms cover downloaded checkpoints or datasets | Not integrated; require checkpoint, data, and dependency review first |
| Spotify Basic Pitch | [spotify/basic-pitch](https://github.com/spotify/basic-pitch) | Apache-2.0 repository | Distributed upstream model; exact artifact terms must still be recorded before bundling | Pitched-instrument AMT sources, not a drum-articulation corpus | **Not applicable to drum classification** | Preserve Apache notices if used for pitched-note features | Rejected as DrumScribe's detector: it is best suited to one pitched instrument at a time and has no 14-class drum head |
| Community Basic-Pitch-style drum adaptation | [Teraldan/drums-audio-to-midi](https://github.com/Teraldan/drums-audio-to-midi) | MIT repository | No released checkpoint located | README describes generated MIDI plus soundfont training; exact source and soundfont rights need audit | **No deployable artifact** | Do not infer dataset or soundfont rights from the code license | Architecture ideas only: 20 drum heads, novelty output, focal loss, CQT features and temporal NMS; no published reproducible accuracy |
| MuScriptor | [muscriptor/muscriptor](https://github.com/muscriptor/muscriptor) | MIT repository code | CC BY-NC 4.0 weights | Mixed research data; production rights unresolved | **No** for current weights | Non-commercial checkpoint restriction blocks a paid launch | Excluded from production; code architecture may be studied without copying restricted weights |
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

## Owner commercial-rights record

The company owner approved hosted commercial inference with ADTOF,
`htdemucs_ft`, and Beat This `final0` for India and international operation on
2026-09-05. Exact source/checkpoint hashes and the permitted-use boundary are
recorded in `docs/legal/COMMERCIAL_MODEL_RIGHTS_APPROVAL.md`. The internal
approval reference is `OWNER-ATTESTATION-2026-09-05`.

This separate grant does not alter the public upstream license offered to other
users. Customer uploads remain inference-only and are not approved for training.

## Production-release gate

Before changing any provider to `commercial_allowed`, record all of the following in
this file and in the deploy configuration:

1. Exact code version/hash and SPDX license.
2. Exact checkpoint hash, its license grant, and redistribution/hosted-inference terms.
3. Training datasets and licenses, including attribution and opt-out obligations.
4. Every material dependency and the production image’s FFmpeg license configuration.
5. Written legal/product approval, contract reference where applicable, regions,
   retention, subprocessors, and whether customer audio may be used for provider training.

The self-hosted Demucs, ADTOF, and Beat This providers are approved under
`OWNER-ATTESTATION-2026-09-05`. Production still fails closed unless that exact
approval reference and explicit confirmation are configured. Other unresolved,
non-commercial, fixture, and mock providers remain blocked. Provider approval
does not by itself satisfy accuracy, infrastructure, privacy, or operational
release gates.

The repository's `drumscribe-events` CRNN architecture has no bundled checkpoint.
Any trained artifact starts as `NEEDS_LEGAL_REVIEW` and may become
`APPROVED_PRODUCTION` only after its exact dataset manifests, augmentation inputs,
Git/config provenance, model SHA-256, evaluation report and required attributions
pass the gate above.
