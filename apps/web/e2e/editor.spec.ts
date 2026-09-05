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

test("guided product tour demonstrates the real editor workflow", async ({ page }) => {
  await page.goto("/projects/demo-groove?tour=1");

  const tour = page.getByTestId("product-tour");
  await expect(tour).toBeVisible();
  await expect(tour.getByText("Audio becomes readable notation.")).toBeVisible();

  await page.getByTestId("tour-next").click();
  await expect(tour.getByText("Attention goes where it matters.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Review 9" })).toHaveClass(/is-active/);

  await page.getByTestId("tour-next").click();
  await expect(tour.getByText("Correct the groove, not a spreadsheet.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit", exact: true })).toHaveClass(/is-active/);

  await page.getByTestId("tour-next").click();
  await expect(tour.getByRole("link", { name: "Open practice" })).toHaveAttribute("href", "/projects/demo-groove/practice");
  await page.getByTestId("tour-next").click();
  await page.getByTestId("tour-export").click();

  await expect(page.getByTestId("export-modal")).toBeVisible();
});
