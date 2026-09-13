# Modal GPU separator

This service runs the owner-approved, hash-verified `htdemucs` checkpoint on one
scale-to-zero Modal L4 GPU. The exact checkpoint is baked into the image and
verified against SHA-256
`8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`,
so cold starts do not download model weights. Requests enter Modal through its
Asia-Pacific South routing region. The endpoint requires Modal proxy authentication, accepts raw audio
at `POST /separate`, and returns a lossless FLAC or WAV drum stem. It permits only one
concurrent GPU container and scales to zero after 30 seconds.

No payment method is attached to the DrumToScore Modal workspace. The dashboard
currently enforces Modal's $1 monthly hard usage limit, so deployment or inference
stops when that allowance is exhausted rather than creating a charge. Do not add a
payment method or raise the limit without the owner's explicit approval.

Deploy from the repository root after `modal setup`:

```sh
modal deploy infra/modal/app.py
```

Create a proxy token for server-to-server calls, then configure the production
worker with the deployed `/separate` URL and the token. Never commit token values:

```dotenv
DRUMSCRIBE_SOURCE_SEPARATION_PROVIDER=demucs
DRUMSCRIBE_DEMUCS_MODEL=htdemucs
DRUMSCRIBE_MODAL_DEMUCS_ENDPOINT=https://prakhargupta267--drumtoscore-separator-drumseparatormumbai-web.ap-south.modal.run/separate
DRUMSCRIBE_MODAL_PROXY_TOKEN_ID=wk-...
DRUMSCRIBE_MODAL_PROXY_TOKEN_SECRET=ws-...
```

Keep the Oracle local Demucs path available as rollback by removing the three
`DRUMSCRIBE_MODAL_*` credential values and restarting the worker.
