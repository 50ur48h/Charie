import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

test("sort_csv sorts numerically and downloads the rows", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  const table = page.getByRole("table", { name: "Top restaurants" });
  await expect(table).toBeVisible();
  const firstCell = () => table.getByRole("cell").first();
  await expect(firstCell()).toHaveText("Uptown");
  await page.getByRole("button", { name: "Sort by Net sales" }).click();
  await expect(firstCell()).toHaveText("Downtown");
  await page.getByRole("button", { name: "Sort by Net sales" }).click();
  await expect(firstCell()).toHaveText("Uptown");
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download table as CSV: Top restaurants" })
    .click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("top-restaurants.csv");
  const path = await file.path();
  expect(path).not.toBeNull();
  const content = await readFile(path as string, "utf-8");
  expect(content).toContain("Restaurant,Net sales");
  expect(content).toContain("Uptown,96200");
});

test("tree renders its explanation region", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await expect(
    page.getByRole("region", { name: "Where the drop came from" }),
  ).toBeVisible();
});

test("method_keyboard expands evidence with the keyboard", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await expect(page.getByText("How I worked this out")).toBeVisible();
  const steps = page.getByRole("button", { name: /Steps/ });
  await steps.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByText("Added up sales by restaurant for October and September."),
  ).toBeVisible();
  const sources = page.getByRole("button", { name: /Sources/ });
  await sources.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Incident log.docx · page 2")).toBeVisible();
});
