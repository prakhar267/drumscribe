export const SUPPORTED_AUDIO_TYPES = [
  "audio/mpeg",
  "audio/wav",
  "audio/x-wav",
  "audio/mp4",
  "audio/x-m4a",
  "audio/aac",
  "audio/flac",
  "audio/x-flac",
] as const;

export const MAX_UPLOAD_BYTES = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_BYTES ?? 150 * 1024 * 1024);
export const MAX_UPLOAD_SECONDS = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_SECONDS ?? 12 * 60);

export type AudioKind = "MP3" | "WAV" | "M4A/AAC" | "FLAC";

export interface ValidatedAudioFile {
  name: string;
  size: number;
  mime: string;
  kind: AudioKind;
}

async function readBlob(blob: Blob) {
  if (typeof blob.arrayBuffer === "function") return blob.arrayBuffer();
  return new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error ?? new Error("Unable to read audio header"));
    reader.readAsArrayBuffer(blob);
  });
}

export function sniffAudioHeader(bytes: Uint8Array): AudioKind | null {
  const ascii = (start: number, length: number) => String.fromCharCode(...bytes.slice(start, start + length));
  if (ascii(0, 4) === "RIFF" && ascii(8, 4) === "WAVE") return "WAV";
  if (ascii(0, 4) === "fLaC") return "FLAC";
  if (ascii(0, 3) === "ID3" || (bytes[0] === 0xff && (bytes[1] & 0xe0) === 0xe0)) return "MP3";
  if (ascii(4, 4) === "ftyp") return "M4A/AAC";
  return null;
}

export async function validateAudioFile(file: File): Promise<ValidatedAudioFile> {
  if (file.size > MAX_UPLOAD_BYTES) throw new Error("This file is larger than the 150 MB upload limit.");
  if (!SUPPORTED_AUDIO_TYPES.includes(file.type as (typeof SUPPORTED_AUDIO_TYPES)[number])) {
    throw new Error("Choose an MP3, WAV, M4A/AAC, or FLAC audio file.");
  }
  const header = new Uint8Array(await readBlob(file.slice(0, 16)));
  const kind = sniffAudioHeader(header);
  if (!kind) throw new Error("This file does not contain recognizable supported audio data.");
  return { name: file.name, size: file.size, mime: file.type, kind };
}

export function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatTime(seconds: number) {
  if (!Number.isFinite(seconds)) return "0:00";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}
