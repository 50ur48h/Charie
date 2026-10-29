import { expect, test, type Page } from "@playwright/test";
import { LEARNER } from "./apps";
import { openLearner } from "./helpers/learner";

// P04.10 responsive pass: every learner screen fits its viewport at tablet
// and phone widths, the drawer opens on phones, wide tables scroll inside
// their card, and dialogs stay inside small screens.
test.use({ timezoneId: "Asia/Kolkata" });

async function noHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

async function dialogFits(page: Page, name: string | RegExp): Promise<void> {
  const dialog = page.getByRole("dialog", { name });
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  const viewport = page.viewportSize();
  expect(box, "dialog has a box").not.toBeNull();
  expect(viewport, "viewport is set").not.toBeNull();
  if (box && viewport) {
    expect(box.x).toBeGreaterThanOrEqual(-1);
    expect(box.y).toBeGreaterThanOrEqual(-1);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
    expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1);
  }
}

test("screens_no_overflow fits every learner screen", async ({ page }) => {
  await page.goto(`${LEARNER}/login?mock=still`);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await noHorizontalOverflow(page);
  await openLearner(page, "/setup", "still");
  for (const step of [1, 2, 3, 4, 5]) {
    await page.goto(`${LEARNER}/setup?step=${step}&mock=still`);
    await expect(page.getByRole("heading", { name: "Set up Charie" })).toBeVisible();
    await noHorizontalOverflow(page);
  }
  for (const path of ["/sources", "/learning", "/knowledge"]) {
    await page.goto(`${LEARNER}${path}?mock=still`);
    await expect(page.locator("#main")).toBeVisible();
    await noHorizontalOverflow(page);
  }
});

test("drawer opens the learner links", async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 0) >= 900, "drawer only below 900 px");
  await openLearner(page, "/sources", "still");
  await page.getByRole("button", { name: "Open menu" }).click();
  const menu = page.getByRole("dialog", { name: "Menu" });
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("link", { name: "Sources" })).toBeVisible();
  await expect(menu.getByRole("link", { name: "Learning" })).toBeVisible();
  await expect(menu.getByRole("link", { name: "Knowledge" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
});

test("wide tables scroll inside their card", async ({ page }) => {
  const phone = (page.viewportSize()?.width ?? 0) < 640;
  await openLearner(page, "/sources", "still");
  const documents = page.getByRole("region", { name: "Documents" });
  await expect(documents).toBeVisible();
  const documentsScroll = await documents.evaluate(
    (el) => ({ scroll: el.scrollWidth, client: el.clientWidth }),
  );
  // The Document column stays 220 px wide, so the table scrolls on phones.
  expect(documentsScroll.scroll).toBeGreaterThan(0);
  if (phone) {
    expect(documentsScroll.scroll).toBeGreaterThan(documentsScroll.client);
  }
  await noHorizontalOverflow(page);

  await page.goto(`${LEARNER}/learning?mock=still`);
  const pastRuns = page.getByRole("region", { name: "Past learning runs" });
  await expect(pastRuns).toBeVisible();
  await noHorizontalOverflow(page);
});
test("dialogs fit the screen", async ({ page }) => {
  await openLearner(page, "/sources", "still");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await dialogFits(page, "Database connection");
  await page.keyboard.press("Escape");

  await page.goto(`${LEARNER}/knowledge?mock=still`);
  await expect(page.getByText("Draft version 15 has 6 changes")).toBeVisible();
  await page.getByRole("button", { name: "Review changes" }).click();
  await dialogFits(page, "Changes in version 15");
  await page.keyboard.press("Escape");

  await page.getByRole("option", { name: /Average order/ }).click();
  await page.getByRole("button", { name: "Mark as wrong" }).click();
  await dialogFits(page, /What's wrong/);
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Publish version 15" }).click();
  await dialogFits(page, "Publish version 15?");
});
