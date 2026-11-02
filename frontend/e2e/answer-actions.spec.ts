import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

async function mockCount(page: import("@playwright/test").Page, kind: string) {
  return page.evaluate(
    (key) => Number(localStorage.getItem(`charie-mock-count-${key}`) ?? "0"),
    kind,
  );
}

test("copy_vote_correction work on the saved answer", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await signedIn(page, CHAT, "/chat/1");
  const actions = page.locator(".answer-actions").first();
  await expect(actions.getByTitle("Copy the answer")).toBeVisible();

  // Copy carries readable prose, never UI button labels.
  await actions.getByTitle("Copy the answer").click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain("October is a good month so far");
  expect(copied).not.toContain("You might also ask");
  expect(copied).not.toContain("This is wrong");
  expect(copied).not.toContain("All numbers checked");
  expect(copied).not.toContain("Copy");

  // Votes toggle and post exactly once per change.
  const up = actions.getByRole("button", { name: "Good answer" });
  await up.click();
  await expect.poll(() => mockCount(page, "feedback")).toBe(1);
  expect(await up.getAttribute("aria-pressed")).toBe("true");
  const down = actions.getByRole("button", { name: "Not helpful" });
  await down.click();
  await expect.poll(() => mockCount(page, "feedback")).toBe(2);
  expect(await down.getAttribute("aria-pressed")).toBe("true");
  expect(await up.getAttribute("aria-pressed")).toBe("false");

  // "This is wrong" sends one correction and reports it to the learner.
  await actions.getByRole("button", { name: "This is wrong" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("What's wrong? Charie's learner will look into it.")).toBeVisible();
  await dialog.getByPlaceholder(/sales should not include/).fill("Trucks are not delivery.");
  const send = dialog.getByRole("button", { name: "Send correction" });
  await send.click();
  await expect(page.getByText("Thanks. Sent to the learner's to-do list.")).toBeVisible();
  await expect.poll(() => mockCount(page, "wrong")).toBe(1);
  await expect(dialog).toBeHidden();
});

test("print_layout hides chrome and shows evidence", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  // Expand the first panel: print must collapse it back to its summary.
  await page.getByRole("button", { name: /Thought for/ }).first().click();
  await expect(page.locator(".thinking-timeline").first()).toBeVisible();
  await expect(page.locator(".method-print").first()).toBeHidden();

  await page.emulateMedia({ media: "print" });
  await expect(page.locator("aside")).toBeHidden();
  await expect(page.getByRole("textbox", { name: "Ask a question" })).toBeHidden();
  await expect(page.locator(".answer-actions").first()).toBeHidden();
  await expect(page.locator(".follow-ups").first()).toBeHidden();
  await expect(page.locator(".thinking-timeline").first()).toBeHidden();
  // The one-line summary and the full method evidence stay readable.
  await expect(page.getByRole("button", { name: /Thought for/ }).first()).toBeVisible();
  await expect(page.locator(".method-print").first()).toBeVisible();
  await expect(page.locator(".method-print").first().getByText("What this means")).toBeVisible();

  await page.emulateMedia({ media: "screen" });
  await expect(page.getByRole("textbox", { name: "Ask a question" })).toBeVisible();
  await expect(page.locator(".answer-actions").first()).toBeVisible();
});

test("fonts_and_charts_ready before printing", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await expect
    .poll(
      () =>
        page.evaluate(() => {
          const charts = [...document.querySelectorAll('[data-chart-container="true"]')];
          return charts.length > 0 && charts.every((chart) => chart.getAttribute("data-chart-ready") === "true");
        }),
      { timeout: 10000 },
    )
    .toBe(true);
});
