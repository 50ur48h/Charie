import { expect, test } from "@playwright/test";
import { CHAT, LEARNER, recordingsReady, signedIn } from "./urls";

test.skip(
  !recordingsReady(),
  "no journey recordings: run `python scripts/e2e_real.py run --record` (needs your yes).",
);

// Journey 3 (P12.4): the chat correction lands in To check, then edit and publish.
test("sees the correction, edits an entry and publishes", async ({ page }) => {
  await signedIn(page, LEARNER, "/knowledge");
  await expect(page.getByRole("heading", { name: "Knowledge", exact: true })).toBeVisible();

  // The chat journey's correction waits under To check.
  await expect(page.getByText("To check")).toBeVisible();
  await expect(page.getByText("Net sales should leave out refunds.")).toBeVisible();

  // Edit the meaning of one entry; keep the old text for the review check.
  const entry = page.getByRole("option").first();
  await expect(entry).toBeVisible();
  await entry.click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const meaning = dialog.getByLabel("Meaning");
  const oldMeaning = await meaning.inputValue();
  expect(oldMeaning.length).toBeGreaterThan(0);
  const newMeaning = `${oldMeaning} (Checked in the e2e journey.)`;
  await meaning.fill(newMeaning);
  await dialog.getByRole("button", { name: "Save change" }).click();
  await expect(page.getByText(/Saved in draft version \d+\./)).toBeVisible();

  // Review changes shows the old and the new meaning side by side.
  await page.getByRole("button", { name: "Review changes" }).click();
  const review = page.getByRole("dialog", { name: /Changes in version \d+/ });
  await expect(review).toBeVisible();
  await expect(review.getByText(oldMeaning)).toBeVisible();
  await expect(review.getByText(newMeaning)).toBeVisible();

  // Publish straight from the review dialog, through the confirm step.
  const publishName = await review.getByRole("button", { name: /Publish version \d+/ }).textContent();
  const published = publishName?.match(/Publish version (\d+)/)?.[1] ?? "";
  expect(published).not.toBe("");
  await review.getByRole("button", { name: /Publish version \d+/ }).click();
  await expect(page.getByText(`Publish version ${published}?`)).toBeVisible();
  await page.getByRole("button", { name: `Publish version ${published}`, exact: true }).last().click();
  await expect(page.getByText(`Version ${published} is live.`)).toBeVisible();

  // The chat app's Settings Data row shows the new version number.
  await page.goto(`${CHAT}/settings`);
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByText(`Knowledge version ${published}`)).toBeVisible();
});
