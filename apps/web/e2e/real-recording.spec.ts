import { expect, test } from "@playwright/test";

const API_BASE = "http://localhost:8000/api/v1";
const recordingPath = process.env.DRUMSCRIBE_REAL_RECORDING_PATH;

test("rights-cleared recording produces a private, editable drum chart", async ({ page }) => {
  test.skip(
    process.env.DRUMSCRIBE_REAL_RECORDING_E2E !== "1" || !recordingPath,
    "Requires the local research stack and a rights-cleared recording path",
  );
  test.setTimeout(900_000);

  await page.goto("/upload");
  await page.getByTestId("audio-file").setInputFiles(recordingPath!);
  await expect(page.getByTestId("file-summary")).toContainText("big-rock-test-45s.mp3");
  await page.getByRole("checkbox").check();
  await page.getByTestId("start-transcription").click();
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]+$/, { timeout: 30_000 });

  const openChart = page.getByTestId("open-chart");
  await expect(openChart).toBeVisible({ timeout: 600_000 });
  const projectId = (await openChart.getAttribute("href"))?.split("/").at(-1);
  expect(projectId).toMatch(/^[0-9a-f-]+$/);

  await openChart.click();
  await expect(page.getByLabel("Project title")).toHaveValue("big-rock-test-45s", { timeout: 30_000 });
  await expect.poll(async () => page.getByTestId("grid-hit").count(), { timeout: 60_000 }).toBeGreaterThan(0);
  await expect(page.getByRole("img", { name: "Engraved drum notation" })).toBeVisible({ timeout: 60_000 });

  const eventsResponse = await page.request.get(`${API_BASE}/projects/${projectId}/events`);
  expect(eventsResponse.ok()).toBeTruthy();
  const events = await eventsResponse.json() as { items: Array<{ confidence: number | null }> };
  expect(events.items.length).toBeGreaterThan(0);

  const originalSigned = await page.request.get(`${API_BASE}/projects/${projectId}/audio/original/url`);
  const drumsSigned = await page.request.get(`${API_BASE}/projects/${projectId}/audio/drums/url`);
  expect(originalSigned.ok()).toBeTruthy();
  expect(drumsSigned.ok()).toBeTruthy();
  const originalUrl = (await originalSigned.json() as { url: string }).url;
  const drumsUrl = (await drumsSigned.json() as { url: string }).url;
  const [original, drums] = await Promise.all([page.request.get(originalUrl), page.request.get(drumsUrl)]);
  expect(original.ok()).toBeTruthy();
  expect(drums.ok()).toBeTruthy();
  const [originalBytes, drumsBytes] = await Promise.all([original.body(), drums.body()]);
  expect(originalBytes.length).toBeGreaterThan(100_000);
  expect(drumsBytes.length).toBeGreaterThan(100_000);
  expect(Buffer.compare(originalBytes, drumsBytes)).not.toBe(0);

  await page.goto(`/projects/${projectId}/settings`);
  await page.getByRole("button", { name: "Delete project" }).click();
  await expect(page.getByText("Project moved to deleted items.")).toBeVisible({ timeout: 60_000 });
  expect((await page.request.get(`${API_BASE}/projects/${projectId}`)).status()).toBe(404);
  expect((await page.request.get(originalUrl)).ok()).toBeFalsy();
  expect((await page.request.get(drumsUrl)).ok()).toBeFalsy();
});
