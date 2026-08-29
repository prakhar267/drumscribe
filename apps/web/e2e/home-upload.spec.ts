import { expect, test } from "@playwright/test";

function tinyWav() {
  const sampleCount = 800;
  const buffer = Buffer.alloc(44 + sampleCount * 2);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + sampleCount * 2, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(8000, 24);
  buffer.writeUInt32LE(16000, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(sampleCount * 2, 40);
  return buffer;
}

test("homepage communicates the product and runs the synchronized demo", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Turn any song into an editable drum chart/i })).toBeVisible();
  await expect(page.getByRole("link", { name: "Transcribe a song" }).first()).toBeVisible();
  const playhead = page.getByTestId("home-playhead");
  const before = await playhead.getAttribute("style");
  await page.getByTestId("demo-play").click();
  await page.waitForTimeout(500);
  await expect(playhead).not.toHaveAttribute("style", before ?? "");
});

test("anonymous upload validates content and reaches background processing", async ({ page }) => {
  await page.goto("/upload");
  await page.getByTestId("audio-file").setInputFiles({ name: "rights-cleared-groove.wav", mimeType: "audio/wav", buffer: tinyWav() });
  await expect(page.getByTestId("file-summary")).toContainText("rights-cleared-groove.wav");
  const start = page.getByTestId("start-transcription");
  await expect(start).toBeDisabled();
  await page.getByRole("checkbox").check();
  await start.click();
  await expect(page).toHaveURL(/\/jobs\/demo-job/);
  await expect(page.getByText("Approximate progress")).toBeVisible();
});
