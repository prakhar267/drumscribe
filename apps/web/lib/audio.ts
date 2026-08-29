const SAMPLE_RATE = 8000;

function writeAscii(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
}

export function createSyntheticDemoAudioUrl(durationSeconds: number, bpm: number) {
  const sampleCount = Math.floor(durationSeconds * SAMPLE_RATE);
  const buffer = new ArrayBuffer(44 + sampleCount * 2);
  const view = new DataView(buffer);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + sampleCount * 2, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, sampleCount * 2, true);
  const beatSeconds = 60 / bpm;
  for (let index = 0; index < sampleCount; index += 1) {
    const time = index / SAMPLE_RATE;
    const beatPhase = time % beatSeconds;
    const halfPhase = time % (beatSeconds / 2);
    const beat = Math.floor(time / beatSeconds);
    const kick = beatPhase < 0.12 ? Math.sin(2 * Math.PI * (72 - beatPhase * 280) * beatPhase) * Math.exp(-beatPhase * 28) : 0;
    const snarePhase = (time - beatSeconds) % (beatSeconds * 2);
    const snare = snarePhase >= 0 && snarePhase < 0.08 ? (Math.sin(index * 12.9898) * 0.45) * Math.exp(-snarePhase * 36) : 0;
    const hat = halfPhase < 0.025 ? (Math.sin(index * 7.13) + Math.sin(index * 3.71)) * 0.08 * Math.exp(-halfPhase * 90) : 0;
    const downbeat = beat % 4 === 0 && beatPhase < 0.08 ? Math.sin(2 * Math.PI * 960 * beatPhase) * 0.08 : 0;
    const sample = Math.max(-1, Math.min(1, kick * 0.58 + snare + hat + downbeat));
    view.setInt16(44 + index * 2, sample * 0x7fff, true);
  }
  return URL.createObjectURL(new Blob([buffer], { type: "audio/wav" }));
}
