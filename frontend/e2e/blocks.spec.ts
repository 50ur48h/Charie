import { expect, test } from "@playwright/test";
import { CHAT } from "./apps";

async function showsFocus(page: import("@playwright/test").Page, target: import("@playwright/test").Locator): Promise<void> {
  await target.focus();
  await expect(target).toBeFocused();
  const sign = await target.evaluate((el) => {
    const style = getComputedStyle(el);
    return {
      outlineWidth: style.outlineWidth,
      outlineStyle: style.outlineStyle,
      boxShadow: style.boxShadow,
    };
  });
  const visible =
    (sign.outlineWidth !== "0px" && sign.outlineStyle !== "none") || sign.boxShadow !== "none";
  expect(visible, "focus sign").toBe(true);
}

test("keyboard focus is visible on the basic blocks", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  const section = page.locator("#basic-blocks");
  await expect(section.getByRole("heading", { name: "Building blocks 1" })).toBeVisible();
  await showsFocus(page, section.getByRole("button", { name: "Ask" }));
  await showsFocus(page, section.getByLabel("Password", { exact: true }));
  await showsFocus(page, section.getByRole("tab", { name: /Waiting/ }));
  await showsFocus(page, section.getByRole("switch", { name: "Remember off" }));
});

test("a wide table scrolls sideways on phones", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  // Table width depends on the real fonts; fallback metrics can fit.
  await page.evaluate(() => document.fonts.ready);
  const table = page.locator("#composite-blocks table").first();
  await expect(table).toBeVisible();
  const box = page.locator("#composite-blocks .overflow-x-auto").first();
  const sizes = await box.evaluate((el) => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
    pageScroll: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }));
  // The table only overflows at phone width; on bigger screens it fits.
  if (sizes.viewport < 500) {
    expect(sizes.scrollWidth).toBeGreaterThan(sizes.clientWidth);
  }
  expect(sizes.pageScroll).toBeLessThanOrEqual(sizes.viewport);
});
