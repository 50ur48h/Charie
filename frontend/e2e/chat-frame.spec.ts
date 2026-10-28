import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

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

test("Finish now stops the running answer once", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/2");
  const messages = page.getByTestId("messages");
  await expect(messages.getByText("Which dishes make us the most profit?", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Finish now" }).click();
  await expect(messages.getByText("Stopped.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Finish now" })).toBeHidden();
  await expect(messages.getByText("Which dishes make us the most profit?", { exact: true })).toBeVisible();
});
