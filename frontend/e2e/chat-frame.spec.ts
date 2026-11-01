import { expect, test, type Page } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

// Holds the chat-detail response back so a second click lands while the page
// is still refreshing. Must run before the first navigation.
async function delayChatDetail(page: Page, ms: number): Promise<void> {
  await page.addInitScript((delay: number) => {
    localStorage.setItem("charie-mock-delay-ms", String(delay));
  }, ms);
}

async function postCount(page: Page, kind: "messages" | "finish"): Promise<string | null> {
  return page.evaluate(
    (key) => localStorage.getItem(key),
    kind === "messages" ? "charie-mock-count-messages" : "charie-mock-count-finish",
  );
}

test("reloading the chat keeps its messages", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  const messages = page.getByTestId("messages");
  await expect(page.getByRole("heading", { name: "How are we doing this month?" })).toBeVisible();
  await expect(messages.getByText("How are we doing this month?", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "How are we doing this month?" })).toBeVisible();
  await expect(
    page.getByTestId("messages").getByText("How are we doing this month?", { exact: true }),
  ).toBeVisible();
});

test("the composer takes multiple lines and an unknown chat is gone", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/3");
  const box = page.getByRole("textbox", { name: "Ask a question" });
  await box.pressSequentially("First line");
  await box.press("Shift+Enter");
  await box.pressSequentially("second line");
  await expect(box).toHaveValue("First line\nsecond line");
  await expect(page).toHaveURL(`${CHAT}/chat/3`);

  await page.goto(`${CHAT}/chat/999`);
  await expect(page.getByRole("heading", { name: "That chat is gone." })).toBeVisible();
});

test("a created chat survives a reload with its answer state", async ({ page }) => {
  await signedIn(page, CHAT, "/");
  await page.getByRole("textbox", { name: "Ask a question" }).fill("Will you remember this?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page).toHaveURL(/\/chat\/\d+/);
  const messages = page.getByTestId("messages");
  await expect(messages.getByText("Will you remember this?", { exact: true })).toBeVisible();
  await page.reload();
  await expect(messages.getByText("Will you remember this?", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Will you remember this?" })).toBeVisible();
  await page.getByRole("button", { name: "Finish now" }).click();
  await expect(messages.getByText("I stopped before finishing. Ask again to get an answer.")).toBeVisible();
  await page.reload();
  await expect(messages.getByText("I stopped before finishing. Ask again to get an answer.")).toBeVisible();
  await expect(messages.getByText("Will you remember this?", { exact: true })).toBeVisible();
});

test("sending stays pending until the refreshed chat is back", async ({ page }) => {
  await delayChatDetail(page, 900);
  await signedIn(page, CHAT, "/chat/3");
  const box = page.getByRole("textbox", { name: "Ask a question" });
  await box.fill("Slow question?");
  await page.getByRole("button", { name: "Ask" }).click();
  const messages = page.getByTestId("messages");
  // The request is answered but the refreshed chat is still held back: the
  // old code unlocked and cleared the draft here, the fixed page does not.
  await expect.poll(() => postCount(page, "messages")).toBe("1");
  await page.waitForTimeout(200);
  await expect(box).toHaveValue("Slow question?");
  // The refreshed chat lands once and stays: the sent question persists,
  // unlike the transient live Thinking indicators (status plus streaming
  // panel) that overlap while the answer streams (P03.7).
  await expect(messages.getByText("Slow question?", { exact: true })).toBeVisible();
  expect(await postCount(page, "messages")).toBe("1");
  await expect(box).toHaveValue("");
});

test("a second Finish now during refresh sends once", async ({ page }) => {
  await delayChatDetail(page, 900);
  await signedIn(page, CHAT, "/chat/2");
  const messages = page.getByTestId("messages");
  const finish = page.getByRole("button", { name: /Finish/ });
  await finish.click();
  // The first request is answered but the refreshed chat is still held back,
  // so this second click lands exactly in the old refresh gap.
  await expect.poll(() => postCount(page, "finish")).toBe("1");
  await finish.dispatchEvent("click");
  await expect(messages.getByText("I stopped before finishing. Ask again to get an answer.")).toBeVisible();
  expect(await postCount(page, "finish")).toBe("1");
});

test("Finish now stops the running answer once", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/2");
  const messages = page.getByTestId("messages");
  await expect(messages.getByText("Which dishes make us the most profit?", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Finish now" }).click();
  await expect(messages.getByText("I stopped before finishing. Ask again to get an answer.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Finish now" })).toBeHidden();
  await expect(messages.getByText("Which dishes make us the most profit?", { exact: true })).toBeVisible();
});
