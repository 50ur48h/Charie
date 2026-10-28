import { expect, test, type Page } from "@playwright/test";
import { CHAT, LEARNER } from "./apps";

const THEME_NAMES = ["Sage", "Lavender", "Mist", "Seafoam", "Mauve", "Slate"];
const EXPECTED_SWATCHES = 38;

async function swatchColors(page: Page): Promise<string[]> {
  return page.$$eval("[data-token]", (swatches) =>
    swatches.map((el) => getComputedStyle(el).backgroundColor),
  );
}

test("shows a swatch for every theme variable", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  await expect(page.getByRole("heading", { name: "Charie kit" })).toBeVisible();
  expect(await page.locator("[data-token]").count()).toBe(EXPECTED_SWATCHES);
});

test("switching theme recolors every swatch", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  await expect(page.locator("[data-token]")).toHaveCount(EXPECTED_SWATCHES);
  const sage = await swatchColors(page);
  for (const name of THEME_NAMES.slice(1)) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", name.toLowerCase());
    const colors = await swatchColors(page);
    expect(colors).toHaveLength(EXPECTED_SWATCHES);
    for (let i = 0; i < EXPECTED_SWATCHES; i += 1) {
      expect(colors[i], `${name} swatch ${i}`).not.toBe(sage[i]);
    }
  }
});

test("remembers the theme after a reload", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  await page.getByRole("button", { name: "Mauve" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "mauve");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "mauve");
});

test("loads the three fonts", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  const families: string[] = await page.evaluate(async () => {
    await document.fonts.ready;
    return [...document.fonts].map((face) => face.family);
  });
  for (const family of ["Inter", "Source Serif 4 Variable", "JetBrains Mono"]) {
    expect(families, family).toContain(family);
  }
});

test("the learner app opens", async ({ page }) => {
  await page.goto(LEARNER);
  await expect(page.locator("html")).toHaveAttribute("data-theme", /.+/);
});
