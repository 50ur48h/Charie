/** The chat shell, in a real browser (WP13.1b). */

import { expect, test, type Page } from "@playwright/test";

import { ANSWER, ids, startStubApi, type StubApi } from "./stub-api";

let api: StubApi;

test.beforeAll(async () => {
  api = await startStubApi();
});

test.beforeEach(() => {
  api.reset();
});

test.afterAll(async () => {
  await api.close();
});

async function signIn(page: Page) {
  await page.goto("/");
  await page.evaluate(() => window.localStorage.setItem("charie.dev-subject", "tester"));
}

test("a member lands in chat, not on an organization page", async ({ page }) => {
  await signIn(page);
  await page.goto("/");

  // The front door redirects into the first organization's chat.
  await expect(page).toHaveURL(new RegExp(`/orgs/${ids.org}/conversations$`));
  // `.first()`, because a client-side redirect briefly has both the page it is leaving and the...
  await expect(
    page.getByRole("heading", { name: "What would you like to know?" }).first(),
  ).toBeVisible();
});

test("asking from the empty chat creates the thread and answers", async ({ page }) => {
  /** The reachability proof for the new home, end to end. */
  await signIn(page);
  await page.goto(`/orgs/${ids.org}/conversations`);

  const box = page.getByLabel("Your question");
  await expect(box).toBeEnabled();
  await box.fill("How many orders were placed in July 2026?");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page).toHaveURL(new RegExp(`/conversations/${ids.conversation}$`));
  await expect(page.getByText(ANSWER)).toBeVisible({ timeout: 20_000 });
});

test("the sidebar collapses, expands, and remembers across a reload", async ({ page }) => {
  await signIn(page);
  await page.goto(`/orgs/${ids.org}/conversations`);

  // The chat list is what the collapsed rail gives up — asserted on rather than on "New chat".
  const thread = page.getByRole("link", { name: "How many orders were placed in July 2026?" });
  await expect(thread).toBeVisible();

  await page.getByRole("button", { name: "Collapse the sidebar" }).click();
  await expect(thread).toBeHidden();

  await page.reload();

  // The point of the test: a real reload, not a remount.
  await expect(page.getByRole("button", { name: "Expand the sidebar" })).toBeVisible();
  await page.getByRole("button", { name: "Expand the sidebar" }).click();
  await expect(thread).toBeVisible();
});

test("dark is chosen, not inherited, and survives a reload", async ({ page }) => {
  /** The property D-046 exists for. */
  await page.emulateMedia({ colorScheme: "dark" });
  await signIn(page);
  await page.goto(`/orgs/${ids.org}/settings`);

  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", "dark");

  await page.getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.reload();
  // Applied by the pre-paint script rather than by React.
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("settings names what is not built, and offers no controls for it", async ({ page }) => {
  await signIn(page);
  await page.goto(`/orgs/${ids.org}/settings`);

  for (const unbuilt of ["System instructions", "Tone", "Preferences"]) {
    await expect(page.getByRole("heading", { name: unbuilt })).toBeVisible();
  }
  await expect(page.getByText("Coming soon")).toHaveCount(3);
  // Honest gap, not a convincing lie: nothing there is pressable.
  await expect(page.getByRole("combobox")).toHaveCount(0);
});

test("the admin screens are reachable from settings, not from the chat", async ({ page }) => {
  await signIn(page);
  await page.goto(`/orgs/${ids.org}/conversations`);

  // The chat carries no admin navigation at all.
  await expect(page.getByRole("link", { name: "Data sources" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Members" })).toHaveCount(0);

  await page.getByRole("link", { name: /Settings/ }).click();
  await expect(page.getByRole("link", { name: "Data sources" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Members" })).toBeVisible();
});

test("the old organization URL still reaches the product", async ({ page }) => {
  // It is in people's history and in older docs, so it redirects rather than 404s.
  await signIn(page);
  await page.goto(`/orgs/${ids.org}`);

  await expect(page).toHaveURL(new RegExp(`/orgs/${ids.org}/conversations$`));
});
