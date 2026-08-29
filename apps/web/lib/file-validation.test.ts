import { describe, expect, it } from "vitest";
import { sniffAudioHeader, validateAudioFile } from "@/lib/file-validation";

const bytes = (value: string) => Uint8Array.from(value.split("").map((character) => character.charCodeAt(0)));

describe("audio validation", () => {
  it("sniffs supported containers instead of trusting extensions", () => {
    expect(sniffAudioHeader(bytes("RIFF0000WAVE0000"))).toBe("WAV");
    expect(sniffAudioHeader(bytes("fLaC000000000000"))).toBe("FLAC");
    expect(sniffAudioHeader(bytes("0000ftypM4A 0000"))).toBe("M4A/AAC");
    expect(sniffAudioHeader(bytes("not audio data!!"))).toBeNull();
  });

  it("rejects MIME and content mismatches", async () => {
    const fake = new File([bytes("not audio data!!")], "fake.wav", { type: "audio/wav" });
    await expect(validateAudioFile(fake)).rejects.toThrow("recognizable supported audio data");
  });

  it("accepts a WAV signature with a supported MIME", async () => {
    const wav = new File([bytes("RIFF0000WAVE0000")], "groove.wav", { type: "audio/wav" });
    await expect(validateAudioFile(wav)).resolves.toMatchObject({ kind: "WAV", name: "groove.wav" });
  });
});
