import { expect, test, type Locator, type Page } from "@playwright/test";
import { CHAT, LEARNER, signedIn } from "./apps";

const CHAT_TITLES = [
  "How are we doing this month?",
  "Top dishes by profit",
  "Why did delivery drop in Austin?",
  "Weekend vs weekday sales",
  "Coupon impact in September",
  "Food waste by restaurant",
  "Best hours to add staff",
  "Dallas vs Houston, last quarter",
];

function isNarrow(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 900;
}

// On phones and tablets the sidebar lives in the menu drawer.
async function sidebarScope(page: Page): Promise<Locator> {
  if (isNarrow(page)) {
    await page.getByRole("button", { name: "Open menu" }).click();
    return page.getByRole("dialog", { name: "Menu" });
  }
  return page.locator("aside");
}

test.beforeEach(async ({ page }) => {
  await signedIn(page, CHAT);
});

test("every chat page opens with its title", async ({ page }) => {
  // P03.1 replaced the "New chat" placeholder with the real page, whose
  // heading is the time-of-day greeting from the Calm home design.
  const pages: [string, string | RegExp][] = [
    ["/", /Good (morning|afternoon|evening)/],
    ["/chat/1", "How are we doing this month?"],
    ["/questions", "Questions for you"],
    ["/knowledge", "Knowledge"],
    ["/usage", "Usage"],
    ["/settings", "Settings"],
  ];
  for (const [path, title] of pages) {
    await page.goto(`${CHAT}${path}`);
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  }
});

test("every learner page opens with its title", async ({ page }) => {
  await signedIn(page, LEARNER, "/setup");
  await page.goto(`${LEARNER}/`);
  await expect(page).toHaveURL(new RegExp(`${LEARNER}/setup(\\?step=\\d)?$`));
  const pages: [string, string][] = [
    ["/setup", "Set up Charie"],
    ["/sources", "Sources"],
    ["/learning", "Learning"],
    ["/knowledge", "Knowledge"],
  ];
  for (const [path, title] of pages) {
    await page.goto(`${LEARNER}${path}`);
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  }
});

test("the sidebar lists the 8 sample chats from the fake API", async ({ page }) => {
  await page.goto(`${CHAT}/`);
  const list = (await sidebarScope(page)).getByTestId("chat-list");
  for (const title of CHAT_TITLES) {
    await expect(list.getByRole("link", { name: title })).toBeVisible();
  }
});

test("clicking a chat opens its page", async ({ page }) => {
  await page.goto(`${CHAT}/`);
  await (await sidebarScope(page))
    .getByTestId("chat-list")
    .getByRole("link", { name: "Top dishes by profit" })
    .click();
  await expect(page).toHaveURL(`${CHAT}/chat/2`);
  await expect(page.getByRole("heading", { name: "Top dishes by profit" })).toBeVisible();
});

test("an unknown address shows Page not found", async ({ page }) => {
  await page.goto(`${CHAT}/nope`);
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await page.getByRole("link", { name: "Go to the start" }).click();
  await expect(page).toHaveURL(`${CHAT}/`);
});
