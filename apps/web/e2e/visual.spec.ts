import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, isMobile }) => {
  test.skip(Boolean(isMobile), "Visual baselines use the fixed desktop viewport");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("homepage visual baseline", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Turn any song into an editable drum chart/i })).toBeVisible();
  await expect(page).toHaveScreenshot("homepage.png", { animations: "disabled", fullPage: true, maxDiffPixelRatio: 0.01 });
});

test("upload visual baseline", async ({ page }) => {
  await page.goto("/upload");
  await expect(page.getByRole("heading", { name: "Drop your recording here" })).toBeVisible();
  await expect(page).toHaveScreenshot("upload.png", { animations: "disabled", fullPage: true, maxDiffPixelRatio: 0.01 });
});

test("engraved editor visual baseline", async ({ page }) => {
  await page.goto("/projects/demo-groove");
  await expect(page.getByTestId("editor")).toBeVisible();
  await expect(page.getByTestId("notation-view")).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
  await expect(page).toHaveScreenshot("editor.png", { animations: "disabled", fullPage: true, maxDiffPixelRatio: 0.01 });
});

test("practice mode visual baseline", async ({ page }) => {
  await page.goto("/projects/demo-groove/practice");
  await expect(page.getByRole("heading", { name: "Neon Room Groove" })).toBeVisible();
  await expect(page.getByTestId("notation-view")).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
  await expect(page).toHaveScreenshot("practice.png", { animations: "disabled", fullPage: true, maxDiffPixelRatio: 0.01 });
});
