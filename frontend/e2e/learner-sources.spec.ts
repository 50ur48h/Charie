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
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Database connection" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Server address").fill("db2.internal");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Connection saved.")).toBeVisible();
  await expect(page.getByText(/Postgres · db2 · read-only login · checked/)).toBeVisible();
});
// P04.5 the Documents section: upload, statuses, remove and retry.
test("an upload goes from New to Reading to Learned", async ({ page }) => {
  await openLearner(page, "/sources", "new");
  await expect(page.getByText("No documents yet. Drop files here to start.")).toBeVisible();
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("button", { name: /Drop files here/ }).click(),
  ]);
  await chooser.setFiles([
    { name: "Extra rules.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 extra") },
  ]);
  await expect(page.getByText("New · not learned yet")).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: "Refresh knowledge base" }).click();
  await expect(page).toHaveURL(/\/learning/);
  // Back client-side: no reload, so the run and its clocks keep going.
  await page.goBack();
  await expect(page.getByText("Reading")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/Learned · \d+ facts/)).toBeVisible({ timeout: 15000 });
});

test("remove asks, then removes", async ({ page }) => {
  await openLearner(page, "/sources", "still");
  await expect(page.getByText("Menu guide, autumn.pdf")).toBeVisible();
  await page.getByRole("button", { name: "Remove" }).first().click();
  const dialog = page.getByRole("dialog", { name: /Remove .*?/ });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("Menu guide, autumn.pdf")).toBeVisible();
  await page.getByRole("button", { name: "Remove" }).first().click();
  const confirm = page.getByRole("dialog", { name: /Remove .*?/ });
  await confirm.getByRole("button", { name: "Remove" }).click();
  await expect(page.getByText(/Removed .*./)).toBeVisible();
});

test("a refused file shows the message", async ({ page }) => {
  await openLearner(page, "/sources", "still");
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("button", { name: /Drop files here/ }).first().click(),
  ]);
  await chooser.setFiles([
    { name: "notes.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") },
  ]);
  await expect(page.getByText("notes.exe can't be added. Charie reads Word, PDF, PowerPoint, Excel, Markdown and text files.")).toBeVisible();
});

// P04.6 editing notes shows the changed line and the banner.
test("editing notes shows the changed line and the banner", async ({ page }) => {
  await openLearner(page, "/sources", "still");
  await expect(page.getByText("Owner notes.md", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Edit notes" }).click();
  const dialog = page.getByRole("dialog", { name: "Your notes" });
  await dialog.getByRole("textbox").fill("Never convert currencies.\nAsk me if anything is unclear.");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("You changed your notes. Charie sorts them again when it next learns.")).toBeVisible();
  await expect(page.getByText("3 new documents and changed notes since the last learning")).toBeVisible();
});
// P07.5 loading a file fills the notes box in the browser.
test("loading notes from a file fills the box", async ({ page }) => {
  await openLearner(page, "/sources", "still");
  await page.getByRole("button", { name: "Edit notes" }).click();
  const dialog = page.getByRole("dialog", { name: "Your notes" });
  await dialog.locator('input[type="file"]').setInputFiles([
    { name: "notes.md", mimeType: "text/markdown", buffer: Buffer.from("# File notes\nA file rule.") },
  ]);
  await expect(dialog.getByRole("textbox")).toHaveValue("# File notes\nA file rule.");
});
