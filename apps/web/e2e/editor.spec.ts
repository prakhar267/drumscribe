import { expect, test } from "@playwright/test";

test("editor adds, deletes, undoes, loops, saves and exports", async ({ page }) => {
  await page.goto("/projects/demo-groove");
  await expect(page.getByTestId("editor")).toBeVisible();
  const engravedScore = page.locator(".notation-engraving > svg");
  await expect(engravedScore).toBeVisible();
  const engravedNote = page.locator("[data-drumscribe-event-id]").first();
  await expect(engravedNote).toHaveAttribute("role", "button");
  await engravedNote.click({ force: true });
  await expect(engravedNote).toHaveClass(/is-selected/);
  const hits = page.getByTestId("grid-hit");
  const initialCount = await hits.count();
  expect(initialCount).toBeGreaterThan(40);

  const grid = page.getByTestId("drum-grid");
  const box = await grid.boundingBox();
  if (!box) throw new Error("Grid is not visible");
  // An early off-beat on the ride-bell row is empty in the deterministic fixture
  // and remains inside the visible portion of the horizontally zoomed canvas.
  await page.mouse.click(box.x + box.width * 0.2, box.y + 30 * 2.5);
  await expect(hits).toHaveCount(initialCount + 1);
  await page.keyboard.press("Delete");
  await expect(hits).toHaveCount(initialCount);
  await page.getByTestId("undo").click();
  await expect(hits).toHaveCount(initialCount + 1);

  await page.getByTestId("loop-toggle").click();
  await expect(page.getByTestId("loop-toggle")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("playback-rate").selectOption("0.5");
  const playhead = page.locator(".notation-playhead");
  const playheadBefore = await playhead.getAttribute("style");
  await page.getByTestId("transport-play").click();
  await page.waitForTimeout(250);
  await page.getByTestId("transport-play").click();
  await expect.poll(() => playhead.getAttribute("style")).not.toBe(playheadBefore);

  await page.waitForTimeout(850);
  await page.reload();
  await expect(page.getByTestId("grid-hit")).toHaveCount(initialCount + 1);

  await page.getByTestId("open-export").click();
  await expect(page.getByTestId("export-modal")).toBeVisible();
  await expect(page.getByTestId("export-midi")).toBeVisible();
});
