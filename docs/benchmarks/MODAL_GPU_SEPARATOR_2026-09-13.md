# Modal GPU separator production gate

Run date: 13 September 2026 (IST)

## Decision

Delegate the production `htdemucs` separation stage to the protected Modal L4
endpoint. Keep the existing Oracle CPU implementation as an immediate
configuration rollback. No payment method was attached or used, and the Modal
workspace retained its $1 hard usage cap.

## Deployment boundary

- App: `drumtoscore-separator`
- Accelerator: one L4 GPU with two vCPUs, maximum one running container
- Scaling: zero idle containers; 30-second scale-down window
- Request route: Asia-Pacific South
- Authentication: server-side Modal proxy token; never exposed to browsers
- Model: Demucs 4.1.0 `htdemucs`
- Checkpoint SHA-256:
  `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`
- Transport: lossless FLAC request and response between Oracle and Modal; the
  application converts the returned stem back to PCM16 WAV for the unchanged
  downstream pipeline

The checkpoint is baked into the image and verified during image construction.
The runtime uses the baked Torch cache and does not need to download weights.

## Same-input speed results

The input was the frozen `rock-100` constructed full mixture from
`output/launch-rights-cleared-fullmix-2026-09-12`, which combines a real GMD
test-split drum performance with a CC BY 3.0 backing. The 180-second probe was
made by repeating that exact 45-second input four times; it is a transport and
runtime capacity check, not a novel song or an accuracy set.

| Input | Modal request duration | Model execution | Observed client total |
| --- | ---: | ---: | ---: |
| 45 seconds, warm | 7.37s | 7.14s | 7.44s |
| 180 seconds, warm | 8.00s | 7.68s | 8.38s |
| 45 seconds, cold with baked checkpoint | 16.0s | 5.59s | 16.48s |
| 180 seconds, cold with baked checkpoint | provider-managed | provider-managed | 20.70s |

A four-vCPU cold-start probe took 26.81s and was rejected in favor of the
cheaper two-vCPU configuration. These observations show that a warm
three-minute separation is well below 20 seconds, but a free scale-to-zero cold
start cannot be promised below 20 seconds because GPU provisioning varies.

An earlier uncompressed WAV transfer took 34.13s client-to-client even though
GPU execution was 7.31s. Lossless FLAC transport removed that network bottleneck.

## Output parity gate

The current Modal output and a fresh local Apple MPS run used the same
45-second input, Demucs 4.1.0 code, `htdemucs` checkpoint and downstream
DrumToScore recall-fusion v6 provider.

| Check | Result |
| --- | ---: |
| Waveform correlation, Modal versus local | **99.712%** |
| Relative waveform RMS difference | 7.587% |
| Signal-to-difference ratio | 22.398 dB |
| Downstream event F1 at 50ms, Modal versus local | **97.356%** |
| Reference F1 at 50ms, Modal | 30.448% |
| Reference F1 at 50ms, local | 31.111% |

The 0.663-point reference-F1 difference is the measured CPU/GPU numerical
variation on this one input. The low absolute reference score is an existing
full-mixture transcription-quality limitation, not a GPU infrastructure result;
it must not be presented as a general product-accuracy percentage.

## Cost and launch guardrails

The Modal billing report after deployment, diagnostics and the validation calls
showed approximately $0.23 of usage before the production end-to-end run. The
workspace has no payment method and a $1 hard cap. H100 and L40S attempts were
rejected by Modal because they required
a payment method; neither became the live deployment. Do not attach a card,
raise the hard cap or select a paid accelerator without fresh founder approval.

To roll back, remove `DRUMSCRIBE_MODAL_DEMUCS_ENDPOINT`,
`DRUMSCRIBE_MODAL_PROXY_TOKEN_ID`, and `DRUMSCRIBE_MODAL_PROXY_TOKEN_SECRET`
from `/etc/drumscribe/drumscribe.env`, then restart the Oracle worker. The
existing `DRUMSCRIBE_DEMUCS_MODEL=htdemucs` setting continues to select the
local CPU model.

## Live production verification

Release `94404af` was deployed to the Oracle API, worker and scheduler. The
worker resolved `demucs-modal-gpu-v1/htdemucs`, reached the protected health
endpoint from inside its container and confirmed the checkpoint hash above.
Cloudflare production version `11b3f1d0-e514-4e9b-bfa5-ed66099d66bf` published
the updated privacy disclosure.

A fresh anonymous browser-equivalent flow created a project, presigned and
uploaded the 45-second rights-cleared `rock-100` WAV, completed the upload,
submitted a job, polled it to `READY`, read its events and timing map, and then
soft-deleted the test project. Job
`8ccadd4c-47d1-4c5a-81ec-e7603d64260c` produced 316 events, 107.14 BPM, 4/4 and
82 timing beats without a retry or job error.

| Production stage | Seconds |
| --- | ---: |
| Validation | 8.6558 |
| Normalization | 7.8859 |
| Modal drum separation, cold | **22.9568** |
| Transcription | 33.5263 |
| Beat detection | 9.3269 |
| Quantization | 4.4173 |
| Score generation | 4.9778 |
| Finalization | 3.7317 |

The Celery task completed in 110.52 seconds; process submission to `READY` took
111.77 seconds. Including anonymous-session creation, project creation and the
browser-equivalent upload, the complete scripted journey took 142.25 seconds.
The recorded model-stage sum fell from 119.23 seconds on the prior Oracle-only
45-second production run to 95.48 seconds, a 19.9% reduction. The cold
separation stage fell from 46.81 to 22.96 seconds; a warm Modal container remains
substantially faster.

The final Modal billing report after the production test was approximately
$0.26, leaving about $0.74 below the existing $1 hard cap. No payment method was
added, opened or used.
