import { expect, test } from "@playwright/test";
import { CHAT, recordingsReady, signedIn } from "./urls";

test.skip(
  !recordingsReady(),
  "no journey recordings: run `python scripts/e2e_real.py run --record` (needs your yes).",
);

async function ask(page: import("@playwright/test").Page, text: string): Promise<void> {
  await page.getByRole("textbox", { name: "Ask a question" }).fill(text);
  await page.getByRole("button", { name: "Ask" }).click();
}

// Journey 2 (P12.4): a full chat on the real back end with saved replies.
test("asks, follows up, picks a choice and uses the extras", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await signedIn(page, CHAT, "/");
  await expect(page.getByRole("textbox", { name: "Ask a question" })).toBeEnabled();

  // The December question: thinking lines, then the summary.
  await ask(page, "How did we do in December 2025?");
  await expect(page.getByRole("button", { name: /Thought for/ }).first()).toBeVisible();
  const answer = page.locator(".answer-actions").first();
  await expect(answer).toBeVisible();

  // Number cards and a chart.
  await expect.poll(() => page.locator(".stat-value").count()).toBeGreaterThan(0);
  await expect
    .poll(() =>
      page.evaluate(() => {
        const charts = [...document.querySelectorAll('[data-chart-container="true"]')];
        return charts.length > 0 && charts.every((chart) => chart.getAttribute("data-chart-ready") === "true");
      }),
    )
    .toBe(true);

  // The November follow-up shows the follow-up was understood.
  await ask(page, "Same for November?");
  await expect(page.getByText("Understood the follow-up")).toBeVisible();

  // The choice question: pick the first option, the answer follows.
  const readings = () => page.getByText(/^I read this as /).count();
  const before = await readings();
  await ask(page, "Which are our best restaurants?");
  const group = page.getByRole("radiogroup").last();
  await expect(group).toBeVisible();
  const choice = group.getByRole("radio").first();
  await choice.click();
  await expect.poll(readings).toBeGreaterThan(before);
  await expect(choice).toBeDisabled();

  // The vote stays on after a reload.
  const up = page.locator(".answer-actions").first().getByRole("button", { name: "Good answer" });
  await up.click();
  await expect(up).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  const upAfter = page.locator(".answer-actions").first().getByRole("button", { name: "Good answer" });
  await expect(upAfter).toHaveAttribute("aria-pressed", "true");

  // Copy carries the answer text.
  const actions = page.locator(".answer-actions").first();
  await actions.getByTitle("Copy the answer").click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied.length).toBeGreaterThan(0);
  expect(copied).not.toContain("This is wrong");

  // The chart image downloads.
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: /^Download as image/ })
    .first()
    .click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.png$/);
  expect(await file.path()).not.toBeNull();

  // "This is wrong" sends the correction the knowledge journey will see.
  await actions.getByRole("button", { name: "This is wrong" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByPlaceholder(/sales should not include/).fill("Net sales should leave out refunds.");
  await dialog.getByRole("button", { name: "Send correction" }).click();
  await expect(page.getByText("Thanks. Sent to the learner's to-do list.")).toBeVisible();

  // Lavender theme: the html element carries it.
  await page.goto(`${CHAT}/settings`);
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByRole("group", { name: "Color theme" }).getByRole("button", { name: "Lavender" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "lavender");

  // Usage shows the budget card and the cost-per-day chart.
  await page.goto(`${CHAT}/usage`);
  await expect(page.locator('div[aria-label^="Budget:"]')).toBeVisible();
  await expect(page.locator('div[aria-label="What each day cost"]')).toBeVisible();
});
