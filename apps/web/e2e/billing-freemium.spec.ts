import { expect, test } from "@playwright/test";

function wav(durationSeconds = 1) {
  const sampleRate = 8_000;
  const sampleCount = sampleRate * durationSeconds;
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
  return buffer;
}

test("pricing explains the free 30-second preview and one-time credit pack", async ({ page }) => {
  await page.goto("/pricing");
  await expect(page.getByRole("heading", { name: /30 seconds free.*Pay only for full songs/ })).toBeVisible();
  await expect(page.getByText("$0", { exact: true })).toBeVisible();
  await expect(page.getByText("$15", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "10 transcriptions" })).toBeVisible();
  await expect(page.getByText("No recurring subscription")).toBeVisible();
});

test("a registered account can preview 30 seconds and sees the full-song paywall", async ({ page }, testInfo) => {
  test.skip(process.env.DRUMSCRIBE_FULL_STACK_E2E !== "1", "requires the real local API");
  test.skip(testInfo.project.name !== "chromium", "one full-stack billing journey is sufficient");

  const email = `billing-${Date.now()}@example.com`;
  await page.goto("/auth");
  await page.getByLabel("Email address").fill(email);
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await page.getByRole("link", { name: "Continue sign-in" }).click();
  await expect(page.getByRole("heading", { name: "You’re signed in." })).toBeVisible();

  await page.goto("/upload");
  await expect(page.getByTestId("credit-status")).toContainText("Free 30-second preview");
  await page.getByTestId("audio-file").setInputFiles({
    name: "rights-cleared-preview.wav",
    mimeType: "audio/wav",
    buffer: wav(),
  });
  await page.getByRole("checkbox").check();
  await page.getByTestId("start-transcription").click();
  await expect(page).toHaveURL(/\/jobs\//);
  await expect(page.getByTestId("open-chart")).toBeVisible({ timeout: 30_000 });

  await page.goto("/upload");
  await expect(page.getByTestId("credit-status")).toContainText("Free 30-second preview");
  await page.getByTestId("audio-file").setInputFiles({
    name: "rights-cleared-full-song.wav",
    mimeType: "audio/wav",
    buffer: wav(31),
  });
  await expect(page.getByTestId("upgrade-before-upload")).toHaveText("Buy credits to continue");
  await expect(page.getByTestId("start-transcription")).toHaveCount(0);
});
