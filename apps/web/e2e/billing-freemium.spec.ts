import { expect, test } from "@playwright/test";

function oneSecondWav() {
  const sampleRate = 8_000;
  const buffer = Buffer.alloc(44 + sampleRate * 2);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + sampleRate * 2, 4);
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
  buffer.writeUInt32LE(sampleRate * 2, 40);
  return buffer;
}

test("pricing explains one free song and the one-time credit pack", async ({ page }) => {
  await page.goto("/pricing");
  await expect(page.getByRole("heading", { name: /One song free.*Pay only when you need more/ })).toBeVisible();
  await expect(page.getByText("$0", { exact: true })).toBeVisible();
  await expect(page.getByText("$15", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "10 transcriptions" })).toBeVisible();
  await expect(page.getByText("No recurring subscription")).toBeVisible();
});

test("a registered account uses its free song and then sees the paywall", async ({ page }, testInfo) => {
  test.skip(process.env.DRUMSCRIBE_FULL_STACK_E2E !== "1", "requires the real local API");
  test.skip(testInfo.project.name !== "chromium", "one full-stack billing journey is sufficient");

  const email = `billing-${Date.now()}@example.com`;
  await page.goto("/auth");
  await page.getByLabel("Email address").fill(email);
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await page.getByRole("link", { name: "Continue sign-in" }).click();
  await expect(page.getByRole("heading", { name: "You’re signed in." })).toBeVisible();

  await page.goto("/upload");
  await expect(page.getByTestId("credit-status")).toContainText("Your first full song is free");
  await page.getByTestId("audio-file").setInputFiles({
    name: "rights-cleared-free-song.wav",
    mimeType: "audio/wav",
    buffer: oneSecondWav(),
  });
  await page.getByRole("checkbox").check();
  await page.getByTestId("start-transcription").click();
  await expect(page).toHaveURL(/\/jobs\//);
  await expect(page.getByTestId("open-chart")).toBeVisible({ timeout: 30_000 });

  await page.goto("/upload");
  await expect(page.getByTestId("credit-status")).toContainText("Your free song has been used");
  await expect(page.getByTestId("upgrade-before-upload")).toHaveText("Buy credits to continue");
  await expect(page.getByTestId("start-transcription")).toHaveCount(0);
});
