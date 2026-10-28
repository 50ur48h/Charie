import { expect, test } from "@playwright/test";
import { CHAT } from "./apps";

test("the dialog keeps focus inside and closes with Escape", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  const section = page.locator("#overlays");
  await section.getByRole("button", { name: "Forget everything" }).click();
  const dialog = page.getByRole("dialog", { name: "Forget everything?" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent);
  expect.soft(focused).toBeTruthy();
  const inside = await dialog.evaluate((el) => el.contains(document.activeElement));
  expect(inside).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("the menu opens with Enter and closes with Escape", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  const trigger = page.locator("#overlays").getByRole("button", { name: "Chat actions" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
});

test("the toast appears and goes away", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  await page.locator("#overlays").getByRole("button", { name: "Show a toast" }).click();
  const toast = page.getByText("Saved. Charie is re-checking what this affects.");
  await expect(toast).toBeVisible();
  await expect(toast).toBeHidden({ timeout: 8000 });
});
