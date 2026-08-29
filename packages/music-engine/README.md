# DrumScribe music engine

`drumscribe-music` is the pure-Python boundary between audio analysis and the
editable DrumScribe event model. The required install has no third-party runtime
dependencies. FFmpeg/FFprobe are invoked with argument arrays and optional research
analysis, Demucs, and ReportLab support live behind extras.

```bash
uv sync --project packages/music-engine --extra dev
uv run --project packages/music-engine pytest
uv run --project packages/music-engine drumscribe-synthetic ./demo --bars 4
```

The synthetic command writes a small rights-cleared WAV plus JSON, MIDI,
MusicXML, and PDF ground truth. It deliberately generates assets at development
time rather than committing binary audio.

Research transcription is a conservative local heuristic, not a production ML
claim. Production code must call `require_production_safe`; unresolved and
non-commercial providers are rejected. See the repository `MODEL_LICENSING.md`.

