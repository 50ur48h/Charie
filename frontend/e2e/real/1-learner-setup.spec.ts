import { existsSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { CHAT, LEARNER, dumpPath, signedIn } from "./urls";

test.skip(!existsSync(dumpPath()), "no e2e dump: run `python scripts/e2e_real.py save` first.");

// Journey 1 (P12.4): the setup guide on the throwaway database, then publish.
test("goes through the setup guide and publishes", async ({ page }) => {
  await signedIn(page, LEARNER, "/setup");
  await expect(page).toHaveURL(new RegExp(`${LEARNER}/setup(\\?step=1)?$`));

  // Step 1: the saved database connection works.
  await expect(page.getByRole("region", { name: "Connect your database" })).toBeVisible();
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByRole("button", { name: "Connection works" })).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  // Step 2: the test document and the owner notes are listed.
  await expect(page.getByRole("region", { name: "Add documents and notes" })).toBeVisible();
  const documents = page.getByRole("list", { name: "Your documents" });
  await expect(documents.getByRole("listitem").first()).toBeVisible();
  await expect(documents.getByText("Owner notes.md")).toBeVisible();
  await expect(documents.getByText("Your rules")).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  // Step 3: the finished learning run shows.
  await expect(page.getByRole("region", { name: "Let Charie learn" })).toBeVisible();
  await expect(page.getByText(/Finished /)).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  // Step 4: at least one question card, each option with its number.
  const step = page.getByRole("region", { name: "Answer its questions" });
  await expect(step).toBeVisible();
  const opener = step.getByRole("button").first();
  await expect(opener).toBeVisible();
  const question = (await opener.getAttribute("aria-label")) ?? (await opener.textContent()) ?? "";
  await opener.click();
  const card = page.getByRole("region", { name: question.trim() });
  const options = card.getByRole("radio");
  await expect(options.first()).toBeVisible();
  for (const option of await options.all()) {
    await expect(option).toHaveAccessibleName(/\d/);
  }
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  // Before step 5, the chat app's New chat page is still learning.
  await page.goto(`${CHAT}/`);
  await expect(page.getByRole("heading", { name: "Charie is still learning" })).toBeVisible();
  await page.goto(`${LEARNER}/setup?step=5`);

  // Step 5 publishes the draft and closes the guide; the question box opens.
  await expect(page.getByRole("region", { name: "Charie is ready" })).toBeVisible();
  await page.getByRole("button", { name: "Open Charie" }).click();
  await expect(page.getByRole("textbox", { name: "Ask a question" })).toBeEnabled();
});
