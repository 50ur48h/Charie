import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

// P03.12 usage on the mocked API: warning/paused states, raising the limit
// and links from the top questions back to their chats.

test.beforeEach(async ({ page }) => {
  await signedIn(page, CHAT, "/usage");
  await expect(page.getByRole("heading", { name: "Usage" })).toBeVisible();
});

test("warning_and_paused banners share the limit dialog", async ({ page }) => {
  // Default demo month: $41.20 of $150, no banner.
  await expect(page.getByText("$41.20")).toBeVisible();
  await expect(page.getByRole("link", { name: /Austin/ }).first()).toBeVisible();
  // Warning state: the banner shows with a manage action.
  await page.evaluate(() => localStorage.setItem("charie-mock-spending", '{"spent_usd": 130}'));
  await page.reload();
  const banner = page.getByRole("status").filter({ has: page.getByRole("button", { name: "Spending limits" }) });
  await expect(banner).toContainText("87% of your credit");
  await banner.getByRole("button", { name: "Spending limits" }).click();
  await expect(page.getByRole("dialog", { name: "Spending limits" })).toBeVisible();
  await page.keyboard.press("Escape");
  // Paused state: questions stop with a plain message and a raise action.
  await page.evaluate(() => localStorage.setItem("charie-mock-spending", '{"spent_usd": 150}'));
  await page.reload();
  const paused = page.getByRole("alert");
  await expect(paused).toContainText("Questions are paused.");
  await paused.getByRole("button", { name: "Raise limit" }).click();
  await expect(page.getByRole("dialog", { name: "Spending limits" })).toBeVisible();
});

test("raise_limit clears the paused state", async ({ page }) => {
  await page.evaluate(() => localStorage.setItem("charie-mock-spending", '{"spent_usd": 150}'));
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Questions are paused.");
  await page.getByRole("button", { name: "Raise limit" }).click();
  const dialog = page.getByRole("dialog", { name: "Spending limits" });
  await dialog.getByLabel("Monthly credit (USD)").fill("300");
  await dialog.getByRole("button", { name: "Save limits" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("alert")).toBeHidden();
  await expect(page.getByText("$150.00")).toBeVisible();
});

test("expensive_chat_link opens the chat that asked it", async ({ page }) => {
  const row = page.getByRole("row", { name: /Why did delivery drop in Austin/ });
  await row.getByRole("link", { name: /Open chat for/ }).click();
  await expect(page).toHaveURL(`${CHAT}/chat/3`);
  await expect(page.getByRole("heading", { name: "Why did delivery drop in Austin?" })).toBeVisible();
});

test("paused_send_blocked stops new questions with a plain message", async ({ page }) => {
  await page.goto(CHAT + "/");
  await page.evaluate(() => localStorage.setItem("charie-mock-spending", JSON.stringify({ spent_usd: 150 })));
  await page.reload();
  await page.getByRole("textbox", { name: "Ask a question" }).fill("Can I still ask?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByText("New AI work is paused because this month's spending limit is reached. Raise the limit on the Usage page to continue.")).toBeVisible();
  await expect(page).toHaveURL(CHAT + "/");
});
