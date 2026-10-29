import { expect, test } from "@playwright/test";
import { openLearner } from "./helpers/learner";

// P04.4 the Sources refresh banner and database card, on the mocked API.
test.use({ timezoneId: "Asia/Kolkata" });

test("banner and database card show the fake data", async ({ page }) => {
  await openLearner(page, "/sources", "still");
  await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible();
  await expect(page.getByText("3 new documents since the last learning")).toBeVisible();
  await expect(page.getByText("Bella Forno database")).toBeVisible();
  await expect(page.getByText("Connected")).toBeVisible();
  await expect(page.getByText(/Postgres · bellaforno-db · read-only login · checked/)).toBeVisible();
  await expect(page.getByText("2.4M")).toBeVisible();
});

test("Edit saves the connection", async ({ page }) => {
  await openLearner(page, "/sources", "still");
  await page.getByRole("button", { name: "Edit" }).click();
  const dialog = page.getByRole("dialog", { name: "Database connection" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Server address").fill("db2.internal");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Connection saved.")).toBeVisible();
  await expect(page.getByText(/Postgres · db2 · read-only login · checked/)).toBeVisible();
});
