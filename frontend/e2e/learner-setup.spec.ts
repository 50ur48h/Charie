import { expect, test, type Page } from "@playwright/test";
import { LEARNER } from "./apps";
import { openLearner } from "./helpers/learner";

// P04.2 the setup guide frame and step 1, P04.3 steps 2-5 and never-show-again,
// all on the mocked API.
test.use({ timezoneId: "Asia/Kolkata" });

async function fillDatabase(page: Page) {
  await page.getByLabel("Server address").fill("db.internal");
  await page.getByLabel("Port").fill("5432");
  await page.getByLabel("Database name").fill("bella_forno");
  await page.getByLabel("Username").fill("charie_readonly");
}

test("design world opens on step 4", async ({ page }) => {
  await openLearner(page, "/setup", "still");
  await expect(page).toHaveURL(`${LEARNER}/setup?step=4`);
  await expect(page.getByRole("heading", { name: "Answer its questions" })).toBeVisible();
  await expect(page.getByText("Step 4 of 5")).toBeVisible();
});

test("new world: test, connect and continue to step 2", async ({ page }) => {
  await openLearner(page, "/setup", "new");
  await expect(page).toHaveURL(`${LEARNER}/setup?step=1`);
  await fillDatabase(page);
  await page.getByLabel("Password").fill("secret");
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByRole("button", { name: "Connection works" })).toBeVisible();
  await expect(page.getByText("57")).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page).toHaveURL(`${LEARNER}/setup?step=2`);
  await expect(page.getByRole("heading", { name: "Add documents and notes" })).toBeVisible();
});

test("a wrong password shows the message", async ({ page }) => {
  await openLearner(page, "/setup", "new");
  await fillDatabase(page);
  await page.getByLabel("Password").fill("wrong");
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText("The username or password is wrong.")).toBeVisible();
});

test("step 2 adds a file and notes", async ({ page }) => {
  await openLearner(page, "/setup", "new");
  await page.goto(`${LEARNER}/setup?step=2&mock=new`);
  await expect(page.getByRole("heading", { name: "Add documents and notes" })).toBeVisible();
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("button", { name: /Drop files here/ }).click(),
  ]);
  await chooser.setFiles([
    { name: "Extra rules.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 extra") },
  ]);
  await expect(page.getByText("Extra rules.pdf")).toBeVisible();
  await expect(page.getByText("Added")).toBeVisible();
  await page.getByRole("button", { name: "Add notes" }).click();
  const dialog = page.getByRole("dialog", { name: "Your notes" });
  await dialog.getByRole("textbox").fill("Never convert currencies.");
  await dialog.getByRole("button", { name: "Save notes" }).click();
  await expect(page.getByText("Notes saved. Charie uses them the next time it learns.")).toBeVisible();
  await expect(page.getByText("Notes added")).toBeVisible();
});

test("step 3 starts learning", async ({ page }) => {
  await openLearner(page, "/setup", "new");
  await page.goto(`${LEARNER}/setup?step=3&mock=new`);
  await expect(page.getByText("Ready to learn")).toBeVisible();
  await page.getByRole("button", { name: "Start learning" }).click();
  await expect(page).toHaveURL(`${LEARNER}/learning`);
});

test("step 4 answers a question", async ({ page }) => {
  await openLearner(page, "/setup", "still");
  await page.goto(`${LEARNER}/setup?step=4&mock=still`);
  await expect(page.getByRole("heading", { name: "Answer its questions" })).toBeVisible();
  await page.getByRole("button", { name: /What should "sales" mean by default/ }).click();
  const first = page.getByRole("region", { name: /What should "sales" mean by default\?/ });
  await first.getByRole("radio", { name: /Without delivery fees/ }).click();
  await first.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByText("Saved. Charie is re-checking what this affects.")).toBeVisible();
  await expect(first).toBeHidden();
  await expect(
    page.getByRole("button", { name: /Are restaurants 9000-9099 test restaurants/ }),
  ).toBeVisible();
});

test("finishing hides the guide for good", async ({ page }) => {
  await openLearner(page, "/setup", "still");
  await page.goto(`${LEARNER}/setup?step=5&mock=still`);
  await expect(page.getByRole("heading", { name: "Charie is ready" })).toBeVisible();
  await page.route("http://localhost:5173/**", (route) =>
    route.fulfill({ body: "<h1>Charie</h1>", contentType: "text/html" }),
  );
  await page.getByRole("button", { name: "Open Charie" }).click();
  await expect(page).toHaveURL("http://localhost:5173/");
  // Back on the learner without ?mock=, the saved setupDone rules: /setup
  // goes to /sources, and the guide leaves the sidebar.
  await page.goto(`${LEARNER}/setup`);
  await expect(page).toHaveURL(`${LEARNER}/sources`);
  await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible();
  if ((page.viewportSize()?.width ?? 0) < 900) {
    // Below 900 px the sidebar lives in a drawer; the topbar logo is visible.
    await expect(page.getByRole("link", { name: "Charie Learner" })).toHaveAttribute(
      "href",
      "/sources",
    );
    await page.getByRole("button", { name: "Open menu" }).click();
    const menu = page.getByRole("dialog", { name: "Menu" });
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("link", { name: "Setup guide" })).toBeHidden();
    await expect(menu.getByRole("link", { name: "Charie Learner" })).toHaveAttribute(
      "href",
      "/sources",
    );
  } else {
    const sidebar = page.locator("aside");
    await expect(sidebar.getByRole("link", { name: "Setup guide" })).toBeHidden();
    await expect(sidebar.getByRole("link", { name: "Charie Learner" })).toHaveAttribute(
      "href",
      "/sources",
    );
  }
});
