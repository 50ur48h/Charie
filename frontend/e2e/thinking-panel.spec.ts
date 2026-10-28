import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

test("a finished answer expands its thinking evidence", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  const panel = page.getByRole("button", { name: /Thought for 38 seconds/ });
  await expect(panel).toBeVisible();
  await panel.click();
  const query = page.getByRole("button", { name: /Added up sales by restaurant/ });
  await query.click();
  // Screen-only scope: the print duplicate carries the same evidence text.
  await expect(page.locator(".thinking-panel").getByText("SELECT restaurant, SUM(net) FROM sales GROUP BY restaurant")).toBeVisible();
  const document = page.getByRole("button", { name: /Read the incident log/ });
  await document.click();
  await expect(page.locator(".thinking-panel").getByText("Downtown delivery was down between 6 and 9 pm.", { exact: false })).toBeVisible();
  await expect(page.locator(".thinking-panel").getByText("Incident log.docx")).toBeVisible();
});

test("a running answer finishes through Finish now", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/2");
  await expect(page.getByText("Thinking…").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Adding up profit by dish/ })).toBeVisible();
  await page.getByRole("button", { name: "Finish now" }).click();
  await expect(page.getByText("Stopped.")).toBeVisible();
  // The panel leaves its running state: no spinner, no live announcement,
  // and no invented summary statistics.
  await expect(page.getByText("Thinking…")).toBeHidden();
  await expect(page.getByText(/Thought for/)).toBeHidden();
  await expect(page.getByRole("button", { name: /Adding up profit by dish/ })).toBeVisible();
});

test("two answers keep their own evidence", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await page.getByRole("button", { name: /Thought for 38 seconds/ }).click();
  await page.getByRole("button", { name: /Thought for 21 seconds/ }).click();
  await expect(page.getByRole("button", { name: /Added up sales by restaurant/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Adding up last year's sales/ })).toBeVisible();
});

test("thinking details open from the keyboard", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await page.getByRole("button", { name: /Thought for 38 seconds/ }).click();
  const query = page.getByRole("button", { name: /Added up sales by restaurant/ });
  await query.focus();
  await page.keyboard.press("Enter");
  // Screen-only scope: the print duplicate carries the same evidence text.
  await expect(page.locator(".thinking-panel").getByText("SELECT restaurant, SUM(net) FROM sales GROUP BY restaurant")).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator(".thinking-panel").getByText("SELECT restaurant, SUM(net) FROM sales GROUP BY restaurant")).toBeHidden();
});

test("a failed answer shows its explanation", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/4");
  await expect(
    page.getByText("The sales extract stopped updating on 24 Oct, so these numbers leave out the last two days."),
  ).toBeVisible();
});
