import { expect, test } from "@playwright/test";
import { LEARNER } from "./apps";
import { openLearner } from "./helpers/learner";

// P04.7 the Learning page on the mocked API. "still" is the design world
// with timers off; "new" runs the clocks for the live checks.
test.use({ timezoneId: "Asia/Kolkata" });

test("matches the fake run", async ({ page }) => {
  await openLearner(page, "/learning", "still");
  await expect(page.getByRole("heading", { name: "Learning", exact: true })).toBeVisible();
  await expect(
    page.getByText("Charie is learning the 3 new documents."),
  ).toBeVisible();
  await expect(page.getByText("62%")).toBeVisible();
  await expect(page.getByText("Learning now")).toBeVisible();
  await expect(
    page.getByText("Step 8 of 12: building and testing business numbers"),
  ).toBeVisible();
  await expect(page.getByText("Tables studied")).toBeVisible();
  await expect(page.getByText("57 / 57").first()).toBeVisible();
  await expect(page.getByText("Steps", { exact: true })).toBeVisible();
  await expect(page.getByText("Read your notes")).toBeVisible();
  await expect(page.getByText("Go live")).toBeVisible();
  await expect(page.getByText("What Charie is finding")).toBeVisible();
  await expect(
    page.getByText("Net sales matches the finance report: Q3 = $3.91M."),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Past learning runs" })).toBeVisible();
  await expect(page.getByText("First learning")).toBeVisible();
  await expect(page.getByText("Draft version 15")).toBeVisible();
});

test("new lines appear live", async ({ page }) => {
  await openLearner(page, "/setup", "new");
  await page.goto(`${LEARNER}/setup?step=3&mock=new`);
  await page.getByRole("button", { name: "Start learning" }).click();
  await expect(page).toHaveURL(`${LEARNER}/learning`);
  await expect(
    page.getByText("Charie is learning your business for the first time."),
  ).toBeVisible();
  await expect(page.getByText("What Charie is finding")).toBeVisible();
  await expect(page.getByText("Net sales matches the finance report: Q3 = $3.91M.")).toBeVisible({
    timeout: 15000,
  });
});

test("pause_reload_resume", async ({ page }) => {
  await openLearner(page, "/learning", "still");
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  // A reload without the mock flag keeps the saved world: still paused,
  // with the saved step counts on screen.
  await page.goto(`${LEARNER}/learning`);
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await expect(
    page.getByText("Learning is paused. Nothing learned so far is lost."),
  ).toBeVisible();
  await expect(page.getByText("62%")).toBeVisible();
  await page.getByRole("button", { name: "Resume" }).click();
  await expect(page.getByText("Learning again.")).toBeVisible();
});

test("failed_run_retry", async ({ page }) => {
  await openLearner(page, "/learning", "failed");
  await expect(
    page.getByText("The last learning run stopped. Nothing learned so far is lost."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(
    page.getByText("Trying again from where it stopped."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
});

test("pause, then resume", async ({ page }) => {
  await openLearner(page, "/learning", "still");
  await expect(page.getByText("Learning now")).toBeVisible();
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await expect(page.getByText("Learning is paused. Nothing learned so far is lost.")).toBeVisible();
  await page.getByRole("button", { name: "Resume" }).click();
  await expect(page.getByText("Learning again.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
});
