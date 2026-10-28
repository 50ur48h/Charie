import { expect, test, type Locator, type Page } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

// P03.9 chat list actions on the mocked API: rename, delete and the
// questions badge. Mock chats persist per browser context, so each test
// starts from the 8 sample chats.
function isNarrow(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 900;
}

// On phones and tablets the sidebar lives in the menu drawer. Reuses the
// open drawer when one is already showing (navigation keeps it mounted).
async function sidebarScope(page: Page): Promise<Locator> {
  if (!isNarrow(page)) return page.locator("aside");
  const drawer = page.getByRole("dialog", { name: "Menu" });
  if (await drawer.isVisible()) return drawer;
  await page.getByRole("button", { name: "Open menu" }).click();
  return drawer;
}

// Closes the drawer so the page behind is usable again (narrow only).
async function closeSidebar(page: Page): Promise<void> {
  if (!isNarrow(page)) return;
  const drawer = page.getByRole("dialog", { name: "Menu" });
  if (await drawer.isVisible()) await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
}

test.beforeEach(async ({ page }) => {
  await signedIn(page, CHAT);
});

async function openChatMenu(scope: Locator, title: string, page: Page): Promise<void> {
  const trigger = scope.getByRole("button", { name: `Chat actions for ${title}` });
  await expect(trigger).toBeVisible();
  // Keyboard-open: every chat menu has a named, Tab-reachable trigger.
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menu")).toBeVisible();
}

test("rename changes the title and keeps it after reload", async ({ page }) => {
  await page.goto(`${CHAT}/`);
  const scope = await sidebarScope(page);
  const list = scope.getByTestId("chat-list");
  await expect(list.getByRole("link", { name: "Top dishes by profit" })).toBeVisible();
  await expect(list.getByText("Today")).toBeVisible();
  await expect(list.getByText("Yesterday")).toBeVisible();

  await openChatMenu(scope, "Top dishes by profit", page);
  await page.getByRole("menuitem", { name: "Rename" }).click();
  const dialog = page.getByRole("dialog", { name: "Rename chat" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Title").fill("Top dishes, renamed");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(list.getByRole("link", { name: "Top dishes, renamed" })).toBeVisible();

  await page.reload();
  const again = (await sidebarScope(page)).getByTestId("chat-list");
  await expect(again.getByRole("link", { name: "Top dishes, renamed" })).toBeVisible();
});

test("cancel_delete keeps the chat", async ({ page }) => {
  await page.goto(`${CHAT}/`);
  const scope = await sidebarScope(page);
  const list = scope.getByTestId("chat-list");
  await openChatMenu(scope, "Weekend vs weekday sales", page);
  await page.getByRole("menuitem", { name: "Delete" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete this chat?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(list.getByRole("link", { name: "Weekend vs weekday sales" })).toBeVisible();
});

test("delete_current removes the chat and goes to the start", async ({ page }) => {
  await page.goto(`${CHAT}/chat/2`);
  await expect(page.getByRole("heading", { name: "Top dishes by profit" })).toBeVisible();
  const scope = await sidebarScope(page);
  await openChatMenu(scope, "Top dishes by profit", page);
  await page.getByRole("menuitem", { name: "Delete" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete this chat?" });
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page).toHaveURL(`${CHAT}/`);
  const home = (await sidebarScope(page)).getByTestId("chat-list");
  await expect(home.getByRole("link", { name: "Top dishes by profit" })).toBeHidden();
  await expect(home.getByRole("link", { name: "How are we doing this month?" })).toBeVisible();
});

test("questions_badge refreshes after sending and keeps the active route", async ({ page }) => {
  await page.goto(`${CHAT}/chat/1`);
  const scope = await sidebarScope(page);
  const questionsLink = scope.getByRole("link", { name: /Questions for you/ });
  await expect(questionsLink).toContainText("3");
  await closeSidebar(page);
  // The mock badge count changes; sending re-reads /api/status.
  await page.evaluate(() => localStorage.setItem("charie-mock-questions-waiting", "1"));
  await page.getByRole("textbox", { name: "Ask a question" }).fill("Anything new?");
  await page.getByRole("button", { name: "Ask" }).click();
  const reopened = await sidebarScope(page);
  const refreshedLink = reopened.getByRole("link", { name: /Questions for you/ });
  await expect(refreshedLink).toContainText("1");
  // The active route stays visible: chat 1 is still the current page.
  await expect(
    reopened.getByRole("link", { name: "How are we doing this month?", exact: true }),
  ).toHaveAttribute("aria-current", "page");
});
