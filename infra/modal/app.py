"""Protected, scale-to-zero GPU source separation for DrumToScore."""

import tempfile
import time
from pathlib import Path

import modal

MODEL = "htdemucs"
CHECKPOINT_SHA256 = "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
MAX_REQUEST_BYTES = 150 * 1024 * 1024
ALLOWED_SUFFIXES = frozenset({".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"})

app = modal.App("drumtoscore-separator")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .uv_pip_install("numpy==2.5.2")
    .uv_pip_install(
        "demucs==4.1.0",
        "fastapi>=0.115,<1",
        "torch==2.13.0",
        "torchaudio==2.11.0",
    )
    .add_local_file(
        Path(__file__).with_name("fetch_htdemucs.py"),
        "/opt/drumtoscore/fetch_htdemucs.py",
        copy=True,
    )
    .run_commands("python /opt/drumtoscore/fetch_htdemucs.py")
    .env(
        {
            "HF_HOME": "/root/.cache/huggingface",
            "HF_HUB_OFFLINE": "1",
            "TORCH_HOME": "/root/.cache/torch",
        }
    )
)


@app.cls(
    image=image,
    gpu="L4",
    cpu=2.0,
    memory=8192,
    min_containers=0,
    max_containers=1,
    scaledown_window=30,
    routing_region="ap-south",
    timeout=600,
    startup_timeout=300,
)
class DrumSeparatorMumbai:
    @modal.enter()
    def load_model(self) -> None:
        import torch
        from demucs.api import Separator

        if not torch.cuda.is_available():
            raise RuntimeError("Modal started the separator without a CUDA GPU")
        self.separator = Separator(
            model=MODEL,
            device="cuda",
            shifts=1,
            split=True,
            overlap=0.25,
            jobs=0,
            progress=False,
        )

    @modal.asgi_app(requires_proxy_auth=True)
    def web(self):
        from demucs.audio import save_audio
        from fastapi import FastAPI, HTTPException, Request, Response

        web_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @web_app.get("/health")
        async def health() -> dict[str, str]:
            return {
                "status": "ready",
                "model": MODEL,
                "modelSha256": CHECKPOINT_SHA256,
                "accelerator": "L4",
            }

        @web_app.post("/separate")
        async def separate(request: Request) -> Response:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > MAX_REQUEST_BYTES:
                        raise HTTPException(status_code=413, detail="audio exceeds 150 MiB")
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail="invalid content length") from exc
            payload = await request.body()
            if not payload:
                raise HTTPException(status_code=400, detail="audio body is empty")
            if len(payload) > MAX_REQUEST_BYTES:
                raise HTTPException(status_code=413, detail="audio exceeds 150 MiB")
            requested_model = request.headers.get("x-drumtoscore-model", MODEL)
            if requested_model != MODEL:
                raise HTTPException(status_code=400, detail=f"model must be {MODEL}")
            supplied_name = request.headers.get("x-drumtoscore-filename", "upload.wav")
            suffix = Path(supplied_name).suffix.casefold()
            if suffix not in ALLOWED_SUFFIXES:
                suffix = ".audio"
            started = time.monotonic()
            with tempfile.TemporaryDirectory(prefix="drumtoscore-modal-") as directory:
                input_path = Path(directory) / f"input{suffix}"
                use_flac = request.headers.get("accept") == "audio/flac"
                output_path = Path(directory) / ("drums.flac" if use_flac else "drums.wav")
                input_path.write_bytes(payload)
                _, stems = self.separator.separate_audio_file(input_path)
                save_audio(
                    stems["drums"],
                    output_path,
                    samplerate=self.separator.samplerate,
                    clip="rescale",
                    bits_per_sample=16,
                )
                result = output_path.read_bytes()
            elapsed_ms = round((time.monotonic() - started) * 1000)
            return Response(
                content=result,
                media_type="audio/flac" if use_flac else "audio/wav",
                headers={
                    "X-DrumToScore-Model": MODEL,
                    "X-DrumToScore-Processing-Ms": str(elapsed_ms),
                    "Cache-Control": "no-store",
                },
            )

        return web_app
