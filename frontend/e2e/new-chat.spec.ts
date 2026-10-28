import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

test("asking opens the new chat", async ({ page }) => {
  await signedIn(page, CHAT, "/");
  await page.getByRole("textbox", { name: "Ask a question" }).fill("How are we doing?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page).toHaveURL(/\/chat\/\d+/);
});

test("Enter asks from the keyboard", async ({ page }) => {
  await signedIn(page, CHAT, "/");
  await page.getByRole("textbox", { name: "Ask a question" }).fill("Top dishes by profit");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/chat\/\d+/);
});

test("the new chat page matches the design", async ({ page }) => {
  await signedIn(page, CHAT, "/");
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  await expect(
    page.getByText("Ask anything about Bella Forno. Charie checks every number before it shows it."),
  ).toBeVisible();
  for (const question of [
    "How are we doing this month?",
    "Which dishes make us the most profit?",
    "Why did delivery drop in Austin last week?",
    "When should we add more staff?",
  ]) {
    await expect(page.getByRole("main").getByRole("button", { name: question })).toBeVisible();
  }
  await expect(page.getByText("3 questions need your answer.")).toBeVisible();
  await expect(page.getByText("Data up to 26 Oct")).toBeVisible();
  await expect(page.getByText("Pick up where you left off")).toBeVisible();
});
