import { expect, test, type Page } from "@playwright/test";

const API_BASE = "http://localhost:8000/api/v1";
const FIXTURE_SECONDS = 12;
const FIXTURE_BPM = 120;

function rightsClearedGrooveWav() {
  const sampleRate = 8_000;
  const sampleCount = sampleRate * FIXTURE_SECONDS;
  const buffer = Buffer.alloc(44 + sampleCount * 2);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + sampleCount * 2, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(sampleCount * 2, 40);
  for (let sample = 0; sample < sampleCount; sample += 1) {
    const beat = sample % 4_000;
    const transient = beat < 160 ? Math.sin((beat / sampleRate) * Math.PI * 220) * Math.exp(-beat / 45) : 0;
    buffer.writeInt16LE(Math.round(transient * 20_000), 44 + sample * 2);
  }
  return buffer;
}

async function requestExport(page: Page, projectId: string, format: "MIDI" | "MUSICXML" | "PDF") {
  const created = await page.request.post(`${API_BASE}/projects/${projectId}/exports`, {
    data: { format },
    headers: { "Idempotency-Key": `e2e-${format.toLowerCase()}-${crypto.randomUUID()}` },
  });
  expect(created.status()).toBe(202);
  const exportId = (await created.json() as { id: string }).id;
  let status = "QUEUED";
  for (let attempt = 0; attempt < 90 && status !== "READY"; attempt += 1) {
    await page.waitForTimeout(500);
    const response = await page.request.get(`${API_BASE}/exports/${exportId}`);
    expect(response.ok()).toBeTruthy();
    status = (await response.json() as { status: string }).status;
    if (status === "FAILED" || status === "CANCELLED") throw new Error(`${format} export ended in ${status}`);
  }
  expect(status).toBe("READY");
  const signed = await page.request.get(`${API_BASE}/exports/${exportId}/download`);
  expect(signed.ok()).toBeTruthy();
  const url = (await signed.json() as { url: string }).url;
  const artifact = await page.request.get(url);
  expect(artifact.ok()).toBeTruthy();
  return { body: await artifact.body(), url };
}

test("real stack covers anonymous upload, conversion, editing, exports and revocable deletion", async ({ page }) => {
  test.skip(process.env.DRUMSCRIBE_FULL_STACK_E2E !== "1", "Requires the full acceptance stack");
  test.setTimeout(240_000);

  await page.goto("/upload");
  await page.getByTestId("audio-file").setInputFiles({
    name: "e2e-rights-cleared-groove.wav",
    mimeType: "audio/wav",
    buffer: rightsClearedGrooveWav(),
  });
  await expect(page.getByTestId("file-summary")).toContainText("e2e-rights-cleared-groove.wav");
  await page.getByRole("checkbox").check();
  await page.getByTestId("start-transcription").click();
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]+$/);
  const jobId = page.url().split("/").at(-1);
  expect(jobId).toMatch(/^[0-9a-f-]+$/);
  // Closing the progress view must not own the job lifecycle. Reopen it from a
  // separate route before waiting for the durable job to finish.
  await page.goto("/");
  await page.goto(`/jobs/${jobId}`);

  const openChart = page.getByTestId("open-chart");
  await expect(openChart).toBeVisible({ timeout: 120_000 });
  const chartHref = await openChart.getAttribute("href");
  const projectId = chartHref?.split("/").at(-1);
  expect(projectId).toMatch(/^[0-9a-f-]+$/);

  // Convert the anonymous owner before editing; the uploaded project must follow.
  await page.goto("/auth");
  await page.getByLabel("Email address").fill(`e2e-${Date.now()}@example.com`);
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  const devContinue = page.getByRole("link", { name: "Continue sign-in" });
  await expect(devContinue).toBeVisible();
  await devContinue.click();
  await expect(page.getByRole("heading", { name: "You’re signed in." })).toBeVisible();

  await page.goto(`/projects/${projectId}`);
  await expect(page.getByTestId("editor")).toBeVisible();
  const hits = page.getByTestId("grid-hit");
  const initialCount = await hits.count();
  expect(initialCount).toBeGreaterThan(0);

  const originalSnare = page.getByRole("button", { name: "Snare hit at 0.50 seconds" });
  await originalSnare.click();
  await page.keyboard.press("Delete");
  await expect(hits).toHaveCount(initialCount - 1);
  await page.getByTestId("undo").click();
  await expect(hits).toHaveCount(initialCount);
  await page.getByTestId("redo").click();
  await expect(hits).toHaveCount(initialCount - 1);

  const grid = page.getByTestId("drum-grid");
  const box = await grid.boundingBox();
  if (!box) throw new Error("Drum grid is not visible");
  // Move the incorrect 0.50-second snare to the next empty sixteenth.
  await page.mouse.click(box.x + box.width * (0.75 / FIXTURE_SECONDS), box.y + 11 * 30 + 15);
  await expect(hits).toHaveCount(initialCount);
  const correctedSnare = page.getByRole("button", { name: "Snare hit at 0.75 seconds" });
  await expect(correctedSnare).toBeVisible();
  await page.getByTestId("undo").click();
  await expect(hits).toHaveCount(initialCount - 1);
  await page.getByTestId("redo").click();
  await expect(hits).toHaveCount(initialCount);

  const waveform = page.getByTestId("editor-waveform");
  const waveformBox = await waveform.boundingBox();
  if (!waveformBox) throw new Error("Waveform is not visible");
  const loopEnd = 4 * 4 * 60 / FIXTURE_BPM;
  const waveformY = waveformBox.y + waveformBox.height / 2;
  await page.mouse.move(waveformBox.x + 2, waveformY);
  await page.mouse.down();
  await page.mouse.move(waveformBox.x + waveformBox.width * (loopEnd / FIXTURE_SECONDS), waveformY);
  await page.mouse.up();
  await expect(page.getByTestId("loop-toggle")).toHaveAttribute("aria-pressed", "true");
  const loopBox = await page.locator(".wave-loop").boundingBox();
  if (!loopBox) throw new Error("Four-measure loop is not visible");
  expect(loopBox.width / waveformBox.width).toBeCloseTo(loopEnd / FIXTURE_SECONDS, 1);

  await page.getByTestId("playback-rate").selectOption("0.5");
  await page.getByTestId("transport-play").click();
  await page.waitForTimeout(300);
  await page.getByTestId("transport-play").click();
  await expect(page.getByRole("button", { name: "All changes saved" })).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByTestId("grid-hit")).toHaveCount(initialCount);
  await expect(page.getByRole("button", { name: "Snare hit at 0.75 seconds" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Snare hit at 0.50 seconds" })).toHaveCount(0);

  const originalSigned = await page.request.get(`${API_BASE}/projects/${projectId}/audio/original/url`);
  expect(originalSigned.ok()).toBeTruthy();
  const originalUrl = (await originalSigned.json() as { url: string }).url;
  expect((await page.request.get(originalUrl)).ok()).toBeTruthy();
  const drumsSigned = await page.request.get(`${API_BASE}/projects/${projectId}/audio/drums/url`);
  expect(drumsSigned.ok()).toBeTruthy();
  const drumsUrl = (await drumsSigned.json() as { url: string }).url;
  expect((await page.request.get(drumsUrl)).ok()).toBeTruthy();
  const waveformSigned = await page.request.get(`${API_BASE}/projects/${projectId}/waveform/url`);
  expect(waveformSigned.ok()).toBeTruthy();
  const waveformUrl = (await waveformSigned.json() as { url: string }).url;
  expect((await page.request.get(waveformUrl)).ok()).toBeTruthy();

  const midi = await requestExport(page, projectId!, "MIDI");
  expect(midi.body.subarray(0, 4).toString("ascii")).toBe("MThd");
  const musicXml = await requestExport(page, projectId!, "MUSICXML");
  expect(musicXml.body.toString("utf8")).toContain("<score-partwise");
  const pdf = await requestExport(page, projectId!, "PDF");
  expect(pdf.body.subarray(0, 5).toString("ascii")).toBe("%PDF-");

  await page.goto(`/projects/${projectId}/settings`);
  await page.getByRole("button", { name: "Delete project" }).click();
  await expect(page.getByText("Project moved to deleted items.")).toBeVisible();
  expect((await page.request.get(`${API_BASE}/projects/${projectId}`)).status()).toBe(404);
  for (const privateUrl of [originalUrl, drumsUrl, waveformUrl, midi.url, musicXml.url, pdf.url]) {
    expect((await page.request.get(privateUrl)).ok()).toBeFalsy();
  }
});
