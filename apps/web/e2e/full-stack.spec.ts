import { expect, test, type Page } from "@playwright/test";

const API_BASE = "http://localhost:8000/api/v1";

function rightsClearedGrooveWav() {
  const sampleRate = 8_000;
  const seconds = 3;
  const sampleCount = sampleRate * seconds;
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
  return artifact.body();
}

test("real stack covers anonymous upload, conversion, editing, exports and revocable deletion", async ({ page }) => {
  test.skip(process.env.DRUMSCRIBE_FULL_STACK_E2E !== "1", "Requires the Compose acceptance stack");
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

  const openChart = page.getByTestId("open-chart");
  await expect(openChart).toBeVisible({ timeout: 120_000 });
  const chartHref = await openChart.getAttribute("href");
  const projectId = chartHref?.split("/").at(-1);
  expect(projectId).toMatch(/^[0-9a-f-]+$/);

  // Convert the anonymous owner before editing; the uploaded project must follow.
  await page.goto("/auth");
  await page.getByLabel("Email address").fill(`e2e-${Date.now()}@example.test`);
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

  const grid = page.getByTestId("drum-grid");
  const box = await grid.boundingBox();
  if (!box) throw new Error("Drum grid is not visible");
  await page.mouse.click(box.x + box.width * 0.37, box.y + box.height - 15);
  await expect(hits).toHaveCount(initialCount + 1);
  await page.keyboard.press("Delete");
  await expect(hits).toHaveCount(initialCount);
  await page.getByTestId("undo").click();
  await expect(hits).toHaveCount(initialCount + 1);
  await page.getByTestId("redo").click();
  await expect(hits).toHaveCount(initialCount);
  await page.getByTestId("undo").click();
  await page.getByTestId("loop-toggle").click();
  await page.getByTestId("playback-rate").selectOption("0.5");
  await page.getByTestId("transport-play").click();
  await page.waitForTimeout(300);
  await page.getByTestId("transport-play").click();
  await expect(page.getByRole("button", { name: "All changes saved" })).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByTestId("grid-hit")).toHaveCount(initialCount + 1);

  const originalSigned = await page.request.get(`${API_BASE}/projects/${projectId}/audio/original/url`);
  expect(originalSigned.ok()).toBeTruthy();
  const originalUrl = (await originalSigned.json() as { url: string }).url;
  expect((await page.request.get(originalUrl)).ok()).toBeTruthy();

  const midi = await requestExport(page, projectId!, "MIDI");
  expect(midi.subarray(0, 4).toString("ascii")).toBe("MThd");
  const musicXml = await requestExport(page, projectId!, "MUSICXML");
  expect(musicXml.toString("utf8")).toContain("<score-partwise");
  const pdf = await requestExport(page, projectId!, "PDF");
  expect(pdf.subarray(0, 5).toString("ascii")).toBe("%PDF-");

  await page.goto(`/projects/${projectId}/settings`);
  await page.getByRole("button", { name: "Delete project" }).click();
  await expect(page.getByText("Project moved to deleted items.")).toBeVisible();
  expect((await page.request.get(`${API_BASE}/projects/${projectId}`)).status()).toBe(404);
  expect((await page.request.get(originalUrl)).ok()).toBeFalsy();
});
