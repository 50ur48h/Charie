import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { CHAT, LEARNER, SAMPLE_PASSWORD, signedIn } from "./apps";

const THEMES = ["sage", "lavender", "mist", "seafoam", "mauve", "slate"] as const;

async function check(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(results.violations).toEqual([]);
}

async function themedSession(page: Page, theme: string): Promise<void> {
  await page.addInitScript(
    (t: string) => {
      localStorage.setItem("charie-theme", t);
      localStorage.setItem("charie-mock-session", "1");
    },
    theme,
  );
}

for (const theme of THEMES) {
  test(`login pages have no axe problems in ${theme} while logged out`, async ({
    page,
  }) => {
    await page.addInitScript((t: string) => {
      localStorage.setItem("charie-theme", t);
    }, theme);
    for (const app of [CHAT, LEARNER]) {
      await page.goto(`${app}/login`);
      await expect(page).toHaveURL(`${app}/login`);
      await expect(
        page.getByRole("heading", { name: "Welcome back" }),
      ).toBeVisible();
      await check(page);
    }
  });

  test(`no axe problems in ${theme}`, async ({ page }) => {
    await themedSession(page, theme);
    await page.goto(`${CHAT}/__kit`);
    await page.waitForTimeout(800);
    await check(page);
    await page.goto(`${CHAT}/__kit/chat-frame`);
    await check(page);
    await page.goto(`${CHAT}/__kit/learner-frame`);
    await check(page);
    await page.goto(`${CHAT}/usage`);
    await check(page);
    await page.goto(`${LEARNER}/sources`);
    await check(page);
  });
}

test("chat_pages_have_no_serious_violations", async ({ page }) => {
  await signedIn(page, CHAT, "/");
  for (const route of ["/", "/chat/1", "/questions", "/knowledge", "/settings"]) {
    await page.goto(`${CHAT}${route}`);
    await expect(page.locator("#main")).toBeVisible();
    await check(page);
  }
});

test("no axe problems on phones", async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 0) >= 900, "phone viewport only");
  await page.goto(`${CHAT}/login`);
  await check(page);
  await page.goto(`${LEARNER}/login`);
  await check(page);
  await signedIn(page, CHAT, "/usage");
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("dialog", { name: "Menu" })).toBeVisible();
  await check(page);
});

test("you can sign in with the keyboard only", async ({ page }) => {
  await page.goto(`${CHAT}/usage`);
  await page.waitForTimeout(800);
  await expect(page).toHaveURL(`${CHAT}/login`);
  await page.locator("body").press("Tab");
  for (let i = 0; i < 10; i += 1) {
    const id = await page.evaluate(() => document.activeElement?.id);
    if (id === "password") break;
    await page.keyboard.press("Tab");
  }
  expect(await page.evaluate(() => document.activeElement?.id)).toBe("password");
  await page.keyboard.type(SAMPLE_PASSWORD);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`${CHAT}/usage`);
  await expect(page.getByRole("heading", { name: "Usage" })).toBeVisible();
});

test("every Tab stop on the kit page shows a focus sign", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  await page.waitForTimeout(800);
  await page.locator("body").press("Tab");
  for (let i = 0; i < 40; i += 1) {
    const sign = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return "none";
      const style = getComputedStyle(el);
      return style.outlineStyle !== "none" && style.outlineWidth !== "0px"
        ? "outline"
        : style.boxShadow !== "none"
          ? "ring"
          : "none";
    });
    expect(sign).not.toBe("none");
    await page.keyboard.press("Tab");
  }
});
