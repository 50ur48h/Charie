import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

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
  const nav = page.viewportSize()!.width < 900
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
