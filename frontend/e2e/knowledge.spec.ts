import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

// P03.11 knowledge (read-only) on the mocked API: search, detail and suggest.

test.beforeEach(async ({ page }) => {
  await signedIn(page, CHAT, "/knowledge");
  await expect(page.getByRole("heading", { name: "Knowledge" })).toBeVisible();
});

test("search_open_suggest finds an entry, opens it and sends a suggestion", async ({
  page,
}) => {
  // Search and kind filters combine: "lunch" in words finds "Lunch".
  await page.getByRole("button", { name: /Words & meanings/ }).click();
  await page.getByLabel("Search everything Charie has learned").fill("lunch");
  await expect(page.getByRole("option", { name: /^"Lunch"/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /^Net sales/ })).toBeHidden();
  await page.getByRole("option", { name: /^"Lunch"/ }).click();
  await expect(page.getByRole("heading", { name: '"Lunch"' })).toBeVisible();
  await expect(page.getByText("Used in 5 answers")).toBeVisible();
  // Suggest a change: the entry stays, the learner gets the note.
  await page.getByRole("button", { name: "Suggest a change" }).click();
  const dialog = page.getByRole("dialog", { name: /Suggest a change/ });
  await dialog.getByLabel("Your suggestion").fill("Lunch should start at 10:30 on weekends.");
  await dialog.getByRole("button", { name: "Send suggestion" }).click();
  await expect(page.getByText("Sent to the Learner to check.")).toBeVisible();
  await expect(page.getByRole("heading", { name: '"Lunch"' })).toBeVisible();
  await expect(page.getByText("Used in 5 answers")).toBeVisible();
});

test("no_edit_controls shows evidence without learner actions", async ({ page }) => {
  await page.getByRole("option", { name: /^Net sales/ }).click();
  await expect(page.getByRole("heading", { name: "Net sales" })).toBeVisible();
  await expect(page.getByText("Confirmed by you")).toBeVisible();
  await expect(page.getByText("How it's worked out")).toBeVisible();
  await expect(page.getByText(/Matches the finance report/)).toBeVisible();
  // Read-only: no Edit, Approve or Mark as wrong controls anywhere.
  await expect(page.getByRole("button", { name: "Edit", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Mark as wrong", exact: true })).toHaveCount(0);
  // An unknown key shows the absent-entry state.
  await page.goto(`${CHAT}/knowledge?entry=no-such-key`);
  await expect(page.getByText("No entry has that key.")).toBeVisible();
});
