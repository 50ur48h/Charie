import fs from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { CHAT } from "./apps";

const READY = '[data-chart-ready="true"]';
const CHART_COUNT = 7;

const TREE_BOXES = [
  "Downtown Austin",
  "Delivery",
  "Outage (14–16 Oct)",
  "Other days",
  "Dine-in",
  "Lunch",
  "Dinner",
  "Pickup",
];

async function chartColors(page: Page): Promise<string[]> {
  return page.$$eval(`${READY} svg`, (svgs) => {
    const ignored = new Set(["none", "transparent", "white", "#fff", "#ffffff"]);
    const colors = new Set<string>();
    for (const svg of svgs) {
      for (const el of svg.querySelectorAll("[fill],[stroke],[stop-color]")) {
        if (el.closest("defs,clipPath")) continue;
        if (
          el.getAttribute("fill-opacity") === "0" ||
          el.getAttribute("stroke-width") === "0" ||
          el.getAttribute("opacity") === "0"
        ) {
          continue;
        }
        for (const attr of ["fill", "stroke", "stop-color"]) {
          const value = el.getAttribute(attr)?.toLowerCase() ?? "";
          if (value && !value.startsWith("url(") && !ignored.has(value)) {
            colors.add(value);
          }
        }
      }
    }
    return [...colors];
  });
}

test("every chart draws as SVG", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  await expect(page.locator(READY)).toHaveCount(CHART_COUNT);
  for (const chart of await page.locator(READY).all()) {
    await expect(chart.locator("svg")).toBeVisible();
    expect(await chart.locator("svg path").count()).toBeGreaterThan(0);
  }
});

test("charts redraw in the new theme colors", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  await expect(page.locator(READY)).toHaveCount(CHART_COUNT);
  const sage = await chartColors(page);
  expect(sage.length).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Lavender", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "lavender");
  await expect
    .poll(async () => chartColors(page))
    .not.toEqual(expect.arrayContaining(sage));
  const lavender = await chartColors(page);
  expect(lavender.filter((c) => sage.includes(c))).toEqual([]);
});

test("charts fit the screen on phones", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  await expect(page.locator(READY)).toHaveCount(CHART_COUNT);
  const viewport = page.viewportSize();
  if (viewport && viewport.width <= 480) {
    for (const figure of await page.locator("[data-figure]").all()) {
      const box = await figure.boundingBox();
      expect(box?.width).toBeLessThanOrEqual(viewport.width);
    }
    const scroller = page
      .locator('[data-figure="Downtown Austin: where the drop comes from"] .overflow-x-auto')
      .first();
    const scroll = await scroller.evaluate((el) => ({
      client: el.clientWidth,
      scroll: el.scrollWidth,
    }));
    expect(scroll.scroll).toBeGreaterThan(scroll.client);
  }
});

test("the tree shows every box", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  const tree = page.getByRole("img", { name: "Downtown Austin: where the drop comes from" });
  await expect(tree).toBeVisible();
  const svg = await tree.locator("svg").innerHTML();
  for (const box of TREE_BOXES) {
    expect(svg, box).toContain(box);
  }
});

test("Download as image saves a PNG", async ({ page }) => {
  await page.goto(`${CHAT}/__kit`);
  await expect(page.locator(READY)).toHaveCount(CHART_COUNT);
  const downloadPromise = page.waitForEvent("download");
  await page
    .locator('[data-figure="Sales change by restaurant"]')
    .getByRole("button", { name: "Download Sales change by restaurant as image" })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("sales-change-by-restaurant.png");
  const path = await download.path();
  const magic = [...fs.readFileSync(path as string).subarray(0, 4)];
  expect(magic).toEqual([0x89, 0x50, 0x4e, 0x47]);
});
