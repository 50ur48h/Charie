import { expect, test, type Page } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

// P03.14 responsive pass: every chat route fits its viewport, the drawer
// keeps keyboard focus honest, long answers don't overflow, and dialogs stay
// inside small screens.

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

test("all_routes_no_overflow fits every route in the viewport", async ({ page }) => {
  // Logged out first: signing in redirects the login page away.
  await page.goto(`${CHAT}/login`);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await noHorizontalOverflow(page);
  await signedIn(page, CHAT, "/");
  for (const route of ["/", "/chat/1", "/questions", "/knowledge", "/usage", "/settings"]) {
    await page.goto(`${CHAT}${route}`);
    await expect(page.locator("#main")).toBeVisible();
    await noHorizontalOverflow(page);
  }
});

test("drawer_keyboard closes the menu and returns focus", async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 0) >= 900, "drawer only below 900 px");
  await signedIn(page, CHAT, "/questions");
  const trigger = page.getByRole("button", { name: "Open menu" });
  await trigger.click();
  await expect(page.getByRole("dialog", { name: "Menu" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Menu" })).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("long_answer keeps the chat inside the viewport", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await expect(page.getByRole("heading", { name: "How are we doing this month?" })).toBeVisible();
  // The whole answer, tables included, fits without sideways scrolling.
  await noHorizontalOverflow(page);
  // The composer stays usable at the bottom.
  const composer = page.getByRole("textbox", { name: "Ask a question" });
  await expect(composer).toBeVisible();
  await composer.fill("And last week?");
  await expect(page.getByRole("button", { name: "Ask" })).toBeEnabled();
});

test("dialogs_fit inside small screens", async ({ page }) => {
  await signedIn(page, CHAT, "/usage");
  await page.getByRole("button", { name: "Spending limits" }).first().click();
  await dialogFits(page, "Spending limits");
  await page.keyboard.press("Escape");

  await page.goto(`${CHAT}/knowledge`);
  await page.getByRole("button", { name: "Suggest a change" }).click();
  await dialogFits(page, /Suggest/);
  await page.keyboard.press("Escape");

  await page.goto(`${CHAT}/settings`);
  await page.getByRole("button", { name: "Change password", exact: true }).click();
  await dialogFits(page, "Change password");
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: /Forget: / }).first().click();
  await dialogFits(page, "Forget this?");
  await page.keyboard.press("Escape");
});
