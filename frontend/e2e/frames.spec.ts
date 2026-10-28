import { expect, test, type Page } from "@playwright/test";
import { CHAT } from "./apps";

const FRAME = `${CHAT}/__kit/chat-frame`;

async function isNarrow(page: Page): Promise<boolean> {
  return (page.viewportSize()?.width ?? 0) < 900;
}

test("the sidebar sits on the left on laptops", async ({ page }) => {
  test.skip(await isNarrow(page), "laptop layout only");
  await page.goto(FRAME);
  const sidebar = page.locator("aside").first();
  await expect(sidebar).toBeVisible();
  await expect(page.getByRole("link", { name: "New chat" })).toBeVisible();
  const sidebarBox = await sidebar.boundingBox();
  const mainBox = await page.locator("#main").boundingBox();
  expect(sidebarBox && mainBox && sidebarBox.x < mainBox.x).toBe(true);
});

test("the menu button opens the drawer, and Escape closes it", async ({ page }) => {
  test.skip(!(await isNarrow(page)), "drawer layout only");
  await page.goto(FRAME);
  await expect(page.locator("aside")).toBeHidden();
  await page.getByRole("button", { name: "Open menu" }).click();
  const drawer = page.getByRole("dialog", { name: "Menu" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("link", { name: "New chat" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(page.getByRole("button", { name: "Open menu" })).toBeFocused();
});

test("the drawer closes when a link is clicked", async ({ page }) => {
  test.skip(!(await isNarrow(page)), "drawer layout only");
  await page.goto(FRAME);
  // Drawer links are plain anchors; stop the click from leaving the demo.
  await page.route((url) => url.pathname !== "/__kit/chat-frame", (route) => route.abort());
  await page.getByRole("button", { name: "Open menu" }).click();
  const drawer = page.getByRole("dialog", { name: "Menu" });
  await expect(drawer).toBeVisible();
  await drawer.getByRole("link", { name: "Usage" }).click();
  await expect(drawer).toBeHidden();
});

test("hiding the sidebar gives the page the full width", async ({ page }) => {
  test.skip(await isNarrow(page), "laptop layout only");
  await page.goto(FRAME);
  const main = page.locator("#main");
  const before = await main.boundingBox();
  await page.getByRole("button", { name: "Hide sidebar" }).click();
  await expect(page.locator("aside")).toBeHidden();
  const after = await main.boundingBox();
  expect(after?.width ?? 0).toBeGreaterThan(before?.width ?? 0);
  await expect(page.getByRole("button", { name: "Show sidebar" })).toBeVisible();
});
