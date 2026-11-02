import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

test("shows the still-learning card and a disabled question box", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("charie-mock-still-learning", "1");
  });
  await signedIn(page, CHAT, "/");
  await expect(page.getByRole("heading", { name: "Charie is still learning" })).toBeVisible();
  await expect(
    page.getByText("It's studying your database and documents.", { exact: false }),
  ).toBeVisible();
  const box = page.getByRole("textbox", { name: "Ask a question" });
  await expect(box).toBeDisabled();
  await expect(box).toHaveAttribute("placeholder", "You can ask once Charie has finished learning.");
  await expect(page.getByRole("link", { name: "Open Learner" })).toBeVisible();
});
