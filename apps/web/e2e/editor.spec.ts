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
  const emptyCell = await grid.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const right = Math.min(rect.right, window.innerWidth) - 12;
    const bottom = Math.min(rect.bottom, window.innerHeight) - 12;
    for (let y = rect.top + 15; y <= bottom; y += 30) {
      for (let x = rect.left + 12; x <= right; x += 18) {
        const target = document.elementFromPoint(x, y);
        if (target?.closest('[data-testid="drum-grid"]') === element && !target.closest(".grid-hit")) return { x, y };
      }
    }
    return null;
  });
  if (!emptyCell) throw new Error("No visible empty grid cell was found");
  await page.mouse.click(emptyCell.x, emptyCell.y);
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
