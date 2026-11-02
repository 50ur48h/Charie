import { expect, test, type Page } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

async function ask(page: Page, text: string) {
  await page.getByRole("textbox", { name: "Ask a question" }).fill(text);
  await page.getByRole("button", { name: "Ask" }).click();
}

test("asks a quick question and continues after a choice", async ({ page }) => {
  const errors: Error[] = [];
  page.on("pageerror", (error) => errors.push(error));
  await signedIn(page, CHAT, "/chat/1");
  await ask(page, "Which are our best restaurants?");
  await expect(page.getByText("How should I rank them?")).toBeVisible();
  await page.getByRole("radio", { name: "By growth" }).click();
  // Picking one plays the usual sample answer for the picked label.
  // Exact words: the played answer also streams the same sentence inside
  // its longer reading paragraph, so a substring match sees two elements.
  await expect(page.getByText("I read this as By growth.", { exact: true })).toBeVisible();
  // The answered quick question keeps its picked card, now unclickable.
  const picked = page.getByRole("radio", { name: "By growth" });
  await expect(picked).toHaveAttribute("data-state", "checked");
  await expect(picked).toBeDisabled();
  expect(errors).toEqual([]);
});
