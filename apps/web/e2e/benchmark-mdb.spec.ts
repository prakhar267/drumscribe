import { mkdir, writeFile } from "node:fs/promises";
import { basename, resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const API_BASE = "http://localhost:8000/api/v1";
const recordingPath = process.env.DRUMSCRIBE_BENCHMARK_RECORDING_PATH;
const outputDirectory = process.env.DRUMSCRIBE_BENCHMARK_OUTPUT_DIR;

async function requestExport(
  page: Page,
  projectId: string,
  format: "MIDI" | "MUSICXML" | "PDF",
) {
  const created = await page.request.post(`${API_BASE}/projects/${projectId}/exports`, {
    data: { format },
    headers: { "Idempotency-Key": `benchmark-${format.toLowerCase()}-${crypto.randomUUID()}` },
  });
  expect(created.status()).toBe(202);
  const exportId = (await created.json() as { id: string }).id;
  let status = "QUEUED";
  for (let attempt = 0; attempt < 120 && status !== "READY"; attempt += 1) {
    await page.waitForTimeout(500);
    const response = await page.request.get(`${API_BASE}/exports/${exportId}`);
    expect(response.ok()).toBeTruthy();
    status = (await response.json() as { status: string }).status;
    if (status === "FAILED" || status === "CANCELLED") {
      throw new Error(`${format} export ended in ${status}`);
    }
  }
  expect(status).toBe("READY");
  const signed = await page.request.get(`${API_BASE}/exports/${exportId}/download`);
  expect(signed.ok()).toBeTruthy();
  const url = (await signed.json() as { url: string }).url;
  const artifact = await page.request.get(url);
  expect(artifact.ok()).toBeTruthy();
  return { body: await artifact.body(), url };
}

test("benchmarks a full mix against MDB Drums ground truth", async ({ page }) => {
  test.skip(
    process.env.DRUMSCRIBE_BENCHMARK_E2E !== "1" || !recordingPath || !outputDirectory,
    "Requires the research stack, MDB full mix, and a benchmark output directory",
  );
  test.setTimeout(900_000);

  const output = resolve(outputDirectory!);
  await mkdir(output, { recursive: true });

  await page.goto("/upload");
  await page.getByTestId("audio-file").setInputFiles(recordingPath!);
  await expect(page.getByTestId("file-summary")).toContainText(basename(recordingPath!));
  await page.getByRole("checkbox").check();
  await page.getByTestId("start-transcription").click();
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]+$/, { timeout: 30_000 });

  const openChart = page.getByTestId("open-chart");
  await expect(openChart).toBeVisible({ timeout: 600_000 });
  const projectId = (await openChart.getAttribute("href"))?.split("/").at(-1);
  if (!projectId) throw new Error("Completed benchmark job did not expose a project id");

  await openChart.click();
  await expect(page.getByLabel("Project title")).toHaveValue("MusicDelta_Beatles_MIX", {
    timeout: 30_000,
  });
  await expect.poll(async () => page.getByTestId("grid-hit").count(), {
    timeout: 60_000,
  }).toBeGreaterThan(0);
  await expect(page.getByRole("img", { name: "Engraved drum notation" })).toBeVisible({
    timeout: 60_000,
  });

  const projectResponse = await page.request.get(`${API_BASE}/projects/${projectId}`);
  const eventsResponse = await page.request.get(`${API_BASE}/projects/${projectId}/events`);
  expect(projectResponse.ok()).toBeTruthy();
  expect(eventsResponse.ok()).toBeTruthy();
  const project = await projectResponse.json();
  const events = await eventsResponse.json();

  const drumsSigned = await page.request.get(`${API_BASE}/projects/${projectId}/audio/drums/url`);
  expect(drumsSigned.ok()).toBeTruthy();
  const drumsUrl = (await drumsSigned.json() as { url: string }).url;
  const drums = await page.request.get(drumsUrl);
  expect(drums.ok()).toBeTruthy();

  const midi = await requestExport(page, projectId, "MIDI");
  const musicXml = await requestExport(page, projectId, "MUSICXML");
  const pdf = await requestExport(page, projectId, "PDF");
  expect(midi.body.subarray(0, 4).toString("ascii")).toBe("MThd");
  expect(musicXml.body.toString("utf8")).toContain("<score-partwise");
  expect(pdf.body.subarray(0, 5).toString("ascii")).toBe("%PDF-");

  await Promise.all([
    writeFile(
      resolve(output, "drumscribe-events.json"),
      JSON.stringify({ project, events }, null, 2),
    ),
    writeFile(resolve(output, "drumscribe-drums.wav"), await drums.body()),
    writeFile(resolve(output, "drumscribe.mid"), midi.body),
    writeFile(resolve(output, "drumscribe.musicxml"), musicXml.body),
    writeFile(resolve(output, "drumscribe.pdf"), pdf.body),
    page.screenshot({ path: resolve(output, "drumscribe-editor.png"), fullPage: true }),
  ]);

  await page.goto(`/projects/${projectId}/settings`);
  await page.getByRole("button", { name: "Delete project" }).click();
  await expect(page.getByText("Project moved to deleted items.")).toBeVisible({ timeout: 60_000 });
  for (const privateUrl of [drumsUrl, midi.url, musicXml.url, pdf.url]) {
    expect((await page.request.get(privateUrl)).ok()).toBeFalsy();
  }
});
