"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, AudioLines, FileAudio, LockKeyhole, Trash2, UploadCloud } from "lucide-react";
import { api } from "@/lib/api/client";
import { formatBytes, formatTime, MAX_UPLOAD_BYTES, MAX_UPLOAD_SECONDS, validateAudioFile, type ValidatedAudioFile } from "@/lib/file-validation";

interface AudioSelection extends ValidatedAudioFile {
  duration: number | null;
  file: File;
}

async function readDuration(file: File) {
  return new Promise<number | null>((resolve) => {
    const audio = document.createElement("audio");
    const source = URL.createObjectURL(file);
    const finish = (value: number | null) => {
      URL.revokeObjectURL(source);
      resolve(value);
    };
    audio.preload = "metadata";
    audio.onloadedmetadata = () => finish(Number.isFinite(audio.duration) ? audio.duration : null);
    audio.onerror = () => finish(null);
    audio.src = source;
  });
}

export function UploadForm() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [selection, setSelection] = useState<AudioSelection | null>(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const selectFile = async (file?: File) => {
    if (!file) return;
    setError(null);
    try {
      const metadata = await validateAudioFile(file);
      const duration = await readDuration(file);
      if (duration !== null && duration > MAX_UPLOAD_SECONDS) throw new Error("This recording is longer than the 12 minute upload limit.");
      setSelection({ ...metadata, duration, file });
    } catch (reason) {
      setSelection(null);
      setError(reason instanceof Error ? reason.message : "We couldn’t read that audio file.");
    }
  };

  const submit = async () => {
    if (!selection || !rightsConfirmed) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.createAndProcessUpload({ file: selection.file, rightsConfirmed: true });
      router.push(`/jobs/${result.jobId}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The upload could not be started. Your file has not been stored; please try again.");
      setSubmitting(false);
    }
  };

  return (
    <div className="upload-layout">
      <section className="surface upload-card" aria-labelledby="upload-card-title">
        <div
          className={`drop-zone${dragging ? " is-dragging" : ""}${selection ? " has-file" : ""}`}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => { event.preventDefault(); setDragging(false); void selectFile(event.dataTransfer.files[0]); }}
          data-testid="drop-zone"
        >
          {!selection ? (
            <>
              <div className="upload-icon"><UploadCloud /></div>
              <h2 id="upload-card-title">Drop your recording here</h2>
              <p>or choose a file from your device</p>
              <button className="button button-primary" type="button" onClick={() => inputRef.current?.click()}>Choose audio</button>
              <input
                className="sr-only"
                ref={inputRef}
                type="file"
                accept=".mp3,.wav,.m4a,.aac,.flac,audio/mpeg,audio/wav,audio/mp4,audio/aac,audio/flac"
                onChange={(event) => void selectFile(event.target.files?.[0])}
                data-testid="audio-file"
              />
            </>
          ) : (
            <div className="file-summary" data-testid="file-summary">
              <div className="file-art"><FileAudio /></div>
              <div style={{ minWidth: 0 }}>
                <p className="file-name">{selection.name}</p>
                <div className="file-meta">
                  <span>{selection.kind}</span>
                  <span>{formatBytes(selection.size)}</span>
                  <span>{selection.duration === null ? "Duration checked securely after upload" : formatTime(selection.duration)}</span>
                </div>
              </div>
              <button className="icon-button file-remove" type="button" aria-label="Remove selected file" onClick={() => { setSelection(null); setRightsConfirmed(false); if (inputRef.current) inputRef.current.value = ""; }}><Trash2 /></button>
            </div>
          )}
        </div>

        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="upload-actions">
          <label className="checkbox-row">
            <input type="checkbox" checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.target.checked)} />
            <span>I have the right to upload and process this audio. I understand my project stays private and is not used to train models without separate consent.</span>
          </label>
          <button className="button button-primary" type="button" disabled={!selection || !rightsConfirmed || submitting} onClick={() => void submit()} data-testid="start-transcription">
            {submitting ? "Starting securely…" : "Create drum chart"}
          </button>
        </div>
      </section>

      <aside className="upload-aside">
        <section className="surface aside-card">
          <h3>What works best</h3>
          <ul><li>Rock, pop, indie and alternative</li><li>Clear, full-length studio recordings</li><li>Straightforward meters and grooves</li></ul>
        </section>
        <section className="surface aside-card">
          <h3><AudioLines size={16} style={{ verticalAlign: "middle", marginRight: 7 }} />File limits</h3>
          <p>MP3, WAV, M4A/AAC or FLAC · up to {Math.round(MAX_UPLOAD_BYTES / 1024 / 1024)} MB · up to {Math.round(MAX_UPLOAD_SECONDS / 60)} minutes.</p>
        </section>
        <section className="surface aside-card">
          <h3><LockKeyhole size={16} style={{ verticalAlign: "middle", marginRight: 7 }} />Private by default</h3>
          <p>Uploads use private storage and short-lived access links. There is no public catalogue.</p>
        </section>
        <div className="notice"><AlertTriangle /><span>Results are an editable first draft. Dense fills and unusual meters may need review.</span></div>
      </aside>
    </div>
  );
}
