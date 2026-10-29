import { expect, test, type Locator, type Page } from "@playwright/test";
import { LEARNER } from "./apps";
import { openLearner } from "./helpers/learner";

// P04.1 learner frame on the mocked API: live badges, Open Charie, worlds.
test.use({ timezoneId: "Asia/Kolkata" });

// Below 900 px the sidebar lives in a drawer, and the page keeps a hidden
// copy behind it: scope badge assertions to the visible copy.
async function sidebar(page: Page): Promise<Locator> {
  if ((page.viewportSize()?.width ?? 0) < 900) {
    await page.getByRole("button", { name: "Open menu" }).click();
    const menu = page.getByRole("dialog", { name: "Menu" });
    await expect(menu).toBeVisible();
    return menu;
  }
  return page.locator("aside");
}

test("badges come from the fake API", async ({ page }) => {
  await openLearner(page);
  await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible();
  const nav = await sidebar(page);
  await expect(nav.getByRole("link", { name: /3 new documents/ })).toBeVisible();
  await expect(nav.getByLabel("Learning now")).toBeVisible();
  await expect(nav.getByRole("link", { name: /4 entries need review/ })).toBeVisible();
  // A reload keeps the store from sessionStorage, badges included.
  await page.reload();
  const again = await sidebar(page);
  await expect(again.getByRole("link", { name: /3 new documents/ })).toBeVisible();
  await expect(again.getByLabel("Learning now")).toBeVisible();
  await expect(again.getByRole("link", { name: /4 entries need review/ })).toBeVisible();
});

test("Open Charie points to chat_url from /api/me", async ({ page }) => {
  await openLearner(page);
  const nav = await sidebar(page);
  const open = nav.getByRole("link", { name: "Open Charie" });
  await expect(open).toHaveAttribute("href", "http://localhost:5173");
  await expect(open).toHaveAttribute("target", "_blank");
  // Same address, straight from the API.
  const me = await page.evaluate(async () => {
    const response = await fetch("/api/me");
    return (await response.json()) as { chat_url: string };
  });
  expect(me.chat_url).toBe("http://localhost:5173");
});

test("mock_new starts empty", async ({ page }) => {
  await openLearner(page, "/sources", "new");
  await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible();
  const nav = await sidebar(page);
  await expect(nav.getByRole("link", { name: /new documents/ })).toBeHidden();
  await expect(nav.getByLabel("Learning now")).toBeHidden();
  // Knowledge entries live outside the learner world's documents and runs
  // (P04.8 owns the draft), so that badge is unchanged in a new world.
  await expect(nav.getByRole("link", { name: /4 entries need review/ })).toBeVisible();
  await expect(page).toHaveURL(`${LEARNER}/sources?mock=new`);
});
