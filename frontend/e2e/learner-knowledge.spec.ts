import { expect, test, type Page } from "@playwright/test";
import { openLearner } from "./helpers/learner";

// P04.8/9 the Learner's Knowledge page on the mocked API: draft banner,
// Needs review, editing, approve, mark-as-wrong, review changes, versions,
// publish and the to-check list.
test.use({ timezoneId: "Asia/Kolkata" });

// The Knowledge nav link carries the review badge; below 900 px it lives
// in the drawer instead of the visible sidebar.
async function expectBadge(page: Page, name: string | RegExp): Promise<void> {
  if ((page.viewportSize()?.width ?? 0) >= 900) {
    await expect(page.getByRole("link", { name })).toBeVisible();
    return;
  }
  await page.getByRole("button", { name: "Open menu" }).click();
  const menu = page.getByRole("dialog", { name: "Menu" });
  await expect(menu.getByRole("link", { name })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
}

test("shows draft 15 and Needs review", async ({ page }) => {
  await openLearner(page, "/knowledge", "still");
  await expect(page.getByRole("heading", { name: "Knowledge", exact: true })).toBeVisible();
  await expect(page.getByText("Draft version 15 has 6 changes")).toBeVisible();
  await expect(page.getByRole("button", { name: "Versions" })).toBeVisible();
  await expectBadge(page, "Knowledge 4 entries need review");
  await expect(page.getByText("To check")).toBeVisible();
  await expect(page.getByText("Net sales should leave out refunds.")).toBeVisible();
  await page.getByRole("button", { name: /Needs review 4/ }).click();
  await expect(page.getByRole("option", { name: /Labor cost %/ })).toBeVisible();
  await expect(page.getByRole("group", { name: "Review filter" }).getByRole("button", { name: "All" })).toBeVisible();
});

test("editing an entry adds a change to the draft", async ({ page }) => {
  await openLearner(page, "/knowledge", "still");
  await page.getByRole("option", { name: /Average order/ }).click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Meaning").fill("Net sales divided by completed orders. Never an average of averages.");
  await page.getByRole("button", { name: "Save change" }).click();
  const detail = page.locator('div[aria-label="Average order"]');
  await expect(detail.getByText("Net sales divided by completed orders. Never an average of averages.")).toBeVisible();
  await expect(page.getByText("Saved in draft version 15.")).toBeVisible();
  await expect(page.getByText("Draft version 15 has 7 changes")).toBeVisible();
});

test("approve confirms an entry", async ({ page }) => {
  await openLearner(page, "/knowledge", "still");
  await page.getByRole("button", { name: /Needs review 4/ }).click();
  await page.getByRole("option", { name: /Labor cost %/ }).click();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("Approved. It goes live in the next version.")).toBeVisible();
  await expect(page.getByText("Draft version 15 has 7 changes")).toBeVisible();
  await expect(page.getByText("Confirmed by you")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: /Needs review 3/ })).toBeVisible();
  await expectBadge(page, "Knowledge 3 entries need review");
});

test("mark as wrong shows the toast and lands in To check", async ({ page }) => {
  await openLearner(page, "/knowledge", "still");
  await page.getByRole("option", { name: /Average order/ }).click();
  await page.getByRole("button", { name: "Mark as wrong" }).click();
  await page.getByLabel("What is wrong?").fill("Average order looks too high.");
  await page.getByRole("button", { name: "Mark as wrong", exact: true }).last().click();
  await expect(page.getByText("Marked as wrong. The Learner will look at it again.")).toBeVisible();
  await expect(page.getByText("Average order: Average order looks too high.")).toBeVisible();
});

test("review changes shows 6 changes", async ({ page }) => {
  await openLearner(page, "/knowledge", "still");
  await page.getByRole("button", { name: "Review changes" }).click();
  await expect(page.getByText("Changes in version 15")).toBeVisible();
  await expect(page.getByText("Big change")).toBeVisible();
  await expect(page.getByText("Why: The autumn menu guide says lunch ends at 2:30 pm.")).toBeVisible();
  await expect(page.getByText("Not in this version")).toHaveCount(4);
});

test("publish makes version 15 live", async ({ page }) => {
  await openLearner(page, "/knowledge", "still");
  await page.getByRole("button", { name: "Publish version 15" }).click();
  await expect(page.getByText("Publish version 15?")).toBeVisible();
  await page.getByRole("button", { name: "Publish version 15", exact: true }).last().click();
  await expect(page.getByText("Version 15 is live.")).toBeVisible();
  await expect(page.getByText("Draft version 15 has")).toBeHidden();
  await expect(page.getByText("Version 15", { exact: true })).toBeVisible();
  await expect(page.getByRole("option", { name: /Refunds come out of sales/ })).toBeVisible();
});

test("real_review_publish_version reviews actual entries then publishes", async ({ page }) => {
  await openLearner(page, "/knowledge", "still");
  await page.getByRole("button", { name: "Review changes" }).click();
  const dialog = page.getByRole("dialog", { name: "Changes in version 15" });
  // The changed lunch entry shows the real before and after meanings.
  await expect(dialog.getByText("Orders placed between 11 am and 3 pm.")).toBeVisible();
  await expect(dialog.getByText("Orders placed between 11 am and 2:30 pm.")).toBeVisible();
  // An added entry carries its real after side and no before side.
  await expect(
    dialog.getByText("Refunds come out of sales; they are not separate income."),
  ).toBeVisible();
  await expect(dialog.getByText("Not in this version")).toHaveCount(4);
  // Publish straight from the review dialog, through the confirm step.
  await dialog.getByRole("button", { name: "Publish version 15" }).click();
  await expect(page.getByText("Publish version 15?")).toBeVisible();
  await page.getByRole("button", { name: "Publish version 15", exact: true }).last().click();
  await expect(page.getByText("Version 15 is live.")).toBeVisible();
  await expect(page.getByText("Draft version 15 has")).toBeHidden();
  await expect(page.getByText("Version 15", { exact: true })).toBeVisible();
});

test("dismiss a to-check item", async ({ page }) => {
  await openLearner(page, "/knowledge", "still");
  await expect(page.getByText("Net sales should leave out refunds.")).toBeVisible();
  const row = page.locator("li", { hasText: "Net sales should leave out refunds." });
  await row.getByRole("button", { name: "Dismiss" }).click();
  await expect(page.getByText("Dismissed. Charie won't look at it.")).toBeVisible();
  await expect(page.getByText("Net sales should leave out refunds.")).toBeHidden();
  await expect(page.getByText('What is a "MEGA deal"?')).toBeVisible();
});

test("versions lists every version newest first", async ({ page }) => {
  await openLearner(page, "/knowledge", "still");
  await page.getByRole("button", { name: "Versions" }).click();
  await expect(page.getByText("Every version of Charie's knowledge.")).toBeVisible();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Version 15")).toBeVisible();
  await expect(dialog.getByText("Version 1", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Live", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Draft", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "See changes" }).first().click();
  await expect(page.getByText("Changes in version 15")).toBeVisible();
});
