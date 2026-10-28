import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

test("kpi, line and diverging states render", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await expect(page.getByText("$1.42M").first()).toBeVisible();
  await expect(page.getByText("+6.2% vs Sep")).toBeVisible();
  await expect(page.getByText("−0.4% vs Sep")).toBeVisible();
  await expect(page.getByText("New guests")).toBeVisible();
  await expect(
    page.getByText("Delivery orders per day", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Sales change by restaurant", { exact: true }).first(),
  ).toBeVisible();
});

test("full_screen expands and closes with Escape", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await page
    .getByRole("button", { name: "Expand: Sales change by restaurant" })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Sales change by restaurant")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("download_png saves the chart", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download as image: Sales change by restaurant" })
    .first()
    .click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("sales-change-by-restaurant.png");
});

test("themes_and_resize keeps charts working", async ({ page }) => {
  const errors: Error[] = [];
  page.on("pageerror", (error) => errors.push(error));
  await signedIn(page, CHAT, "/chat/1");
  const chart = page.getByRole("img", { name: /Sales change by restaurant/ }).first();
  await expect(chart).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(chart).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("themechange")));
  await expect(chart).toBeVisible();
  expect(errors).toEqual([]);
});
