import { expect, test } from "@playwright/test";
import { CHAT, LEARNER, signedIn } from "./apps";
import { openLearner } from "./helpers/learner";

// P03.10 questions on the mocked API: answer, skip, tabs and ask-about.

test.beforeEach(async ({ page }) => {
  await signedIn(page, CHAT, "/questions");
  await expect(page.getByRole("heading", { name: "Questions for you" })).toBeVisible();
});

test("answer_skip_change updates tabs and the badge", async ({ page }) => {
  // Three waiting questions; the badge counts them.
  await expect(page.getByRole("tab", { name: /Waiting/ })).toContainText("3");
  // Answer the first: pick the second option and save.
  const first = page.getByRole("region", { name: /What should "sales" mean by default\?/ });
  await first.getByRole("radio", { name: /Without delivery fees/ }).click();
  await first.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByText("Saved. Charie is re-checking what this affects.")).toBeVisible();
  await expect(first).toBeHidden();
  await expect(page.getByRole("tab", { name: /Waiting/ })).toContainText("2");
  await expect(page.getByRole("tab", { name: /Answered/ })).toContainText("4");
  // Skip the next waiting question; the skip keeps the default.
  const second = page.getByRole("region", { name: /Are restaurants 9000-9099 test restaurants\?/ });
  await second.getByRole("button", { name: "Skip for now" }).click();
  await expect(second).toBeHidden();
  await expect(page.getByRole("tab", { name: /Waiting/ })).toContainText("1");
  await expect(page.getByRole("tab", { name: /Skipped/ })).toContainText("2");
  // The badge follows the waiting count (in the drawer on narrow screens).
  if ((page.viewportSize()?.width ?? 0) < 900) {
    await page.getByRole("button", { name: "Open menu" }).click();
  }
  const nav =
    page.viewportSize()!.width < 900
      ? page.getByRole("dialog", { name: "Menu" })
      : page.locator("aside");
  await expect(nav.getByRole("link", { name: /Questions for you/ })).toContainText("1");
  // The drawer covered the page; close it before using the tabs.
  if ((page.viewportSize()?.width ?? 0) < 900) {
    await page.keyboard.press("Escape");
  }
  // Change the earlier answer from the Answered tab.
  await page.getByRole("tab", { name: /Answered/ }).click();
  await expect(page.getByText("Last full week, Monday to Sunday")).toBeVisible();
  // Change opens the saved answer for editing: exactly one option is pre-selected.
  await page.getByRole("button", { name: /Change your answer to.*last week/ }).click();
  const answered = page.getByRole("region", { name: /What does "last week" mean/ });
  await expect(answered.getByRole("radio", { checked: true })).toHaveCount(1);
  await expect(
    answered.getByRole("radio", { name: "Last full week, Monday to Sunday", checked: true }),
  ).toBeVisible();
  // Pick a different option and save; the row shows the new saved answer.
  await answered.getByRole("radio", { name: "The last 7 days" }).click();
  await answered.getByRole("button", { name: "Save answer" }).click();
  // Both saves toast, so the earlier toast may still be on screen; check the latest.
  await expect(
    page.getByText("Saved. Charie is re-checking what this affects.").last(),
  ).toBeVisible();
  await expect(page.getByText("The last 7 days")).toBeVisible();
  await expect(page.getByText("Last full week, Monday to Sunday")).toBeHidden();
});

test("tabs_badge shows empty states and counts", async ({ page }) => {
  await page.getByRole("tab", { name: /Skipped/ }).click();
  await expect(page.getByText("Was the Austin outage a one-off?")).toBeVisible();
  await page.getByRole("tab", { name: /Answered/ }).click();
  await expect(page.getByText("More than 5%, or more than $5K")).toBeVisible();
});

test("ask_about_question fills a new-chat draft", async ({ page }) => {
  const first = page.getByRole("region", { name: /What should "sales" mean by default\?/ });
  await first.getByRole("button", { name: "Ask Charie about this" }).click();
  await expect(page).toHaveURL(/\?draft=/);
  await expect(page.getByRole("textbox", { name: "Ask a question" })).toHaveValue(
    'What should "sales" mean by default?',
  );
});
test("answer_refresh_badge follows the waiting count", async ({ page }) => {
  await expect(page.getByRole("tab", { name: /Waiting/ })).toContainText("3");
  const first = page.getByRole("region", { name: /What should "sales" mean by default\?/ });
  await first.getByRole("radio", { name: /Without delivery fees/ }).click();
  await first.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByText("Saved. Charie is re-checking what this affects.")).toBeVisible();
  await expect(first).toBeHidden();
  await expect(page.getByRole("tab", { name: /Waiting/ })).toContainText("2");
  if ((page.viewportSize()?.width ?? 0) < 900) {
    await page.getByRole("button", { name: "Open menu" }).click();
  }
  const nav =
    page.viewportSize()!.width < 900
      ? page.getByRole("dialog", { name: "Menu" })
      : page.locator("aside");
  await expect(nav.getByRole("link", { name: /Questions for you/ })).toContainText("2");
});

test("change_answer updates the saved answer", async ({ page }) => {
  const first = page.getByRole("region", { name: /What should "sales" mean by default\?/ });
  await first.getByRole("radio", { name: /Without delivery fees/ }).click();
  await first.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByText("Saved. Charie is re-checking what this affects.")).toBeVisible();
  await page.getByRole("tab", { name: /Answered/ }).click();
  await page.getByRole("button", { name: /Change your answer to.*sales/ }).click();
  const answered = page.getByRole("region", { name: /What should "sales" mean by default\?/ });
  await expect(answered.getByRole("radio", { checked: true })).toHaveCount(1);
  await answered.getByRole("radio", { name: "Including delivery fees" }).click();
  await answered.getByRole("button", { name: "Save answer" }).click();
  await expect(
    page.getByText("Saved. Charie is re-checking what this affects.").last(),
  ).toBeVisible();
  await expect(answered).toBeHidden();
  await expect(page.getByText("Including delivery fees")).toBeVisible();
});

test("setup_question_shared answers from the setup step", async ({ page }) => {
  await openLearner(page);
  await page.goto(`${LEARNER}/setup?step=4`);
  await expect(page.getByRole("heading", { name: "Answer its questions" })).toBeVisible();
  await expect(page.getByText(/3 things/)).toBeVisible();
  await page.getByRole("button", { name: /What should "sales" mean by default\?/ }).click();
  const card = page.getByRole("region", { name: /What should "sales" mean by default\?/ });
  await card.getByRole("radio", { name: /Without delivery fees/ }).click();
  await card.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByText("Saved. Charie is re-checking what this affects.")).toBeVisible();
  await expect(card).toBeHidden();
  await expect(page.getByText(/2 things/)).toBeVisible();
});
