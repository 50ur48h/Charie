/** The Phase 7 gate, in a real browser (B-044). */

import { expect, test } from "@playwright/test";

import { ANSWER, CHART_SPEC, QUESTION, ids, startStubApi, type StubApi } from "./stub-api";

let api: StubApi;

test.beforeAll(async () => {
  api = await startStubApi();
});

test.beforeEach(() => {
  api.reset();
});

test.afterAll(async () => {
  await api.close();
});

/** Sign in the way `lib/auth/dev-tokens.ts` does: remember a subject. */
async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.evaluate(() => window.localStorage.setItem("charie.dev-subject", "tester"));
}

async function openConversation(page: import("@playwright/test").Page) {
  await signIn(page);
  await page.goto(`/orgs/${ids.org}/conversations/${ids.conversation}`);
  await expect(page.getByLabel("Ask a question")).toBeVisible();
}

/** Open an answer's Evidence disclosure. */
async function openEvidence(page: import("@playwright/test").Page) {
  await page.getByText("Evidence", { exact: true }).first().click();
}

async function ask(page: import("@playwright/test").Page) {
  await page.getByLabel("Ask a question").fill(QUESTION);
  await page.getByRole("button", { name: "Send" }).click();
}

test("the answer appears after one question, with no further interaction", async ({ page }) => {
  await openConversation(page);
  await ask(page);

  // The question is accepted immediately and the run is watched.
  await expect(page.getByText("working")).toBeVisible();

  // And then — with nothing else touched — the answer arrives.
  await expect(page.getByText(ANSWER)).toBeVisible({ timeout: 15_000 });
  // `exact`: the shell adds ancestors that also contain this word (WP13.1b).
  await expect(page.getByText("answered", { exact: true })).toBeVisible();
});

test("the citation opens into the query behind the answer", async ({ page }) => {
  await openConversation(page);
  await ask(page);
  await expect(page.getByText(ANSWER)).toBeVisible({ timeout: 15_000 });

  await openEvidence(page);

  // No second click: a finding with one citation shows its query outright (D-047).
  await expect(page.getByText(/SELECT COUNT\(\*\) AS "order_count"/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "3718" })).toBeVisible();
});

test("the answer is shown once, not twice", async ({ page }) => {
  await openConversation(page);
  await ask(page);
  await expect(page.getByText(ANSWER)).toBeVisible({ timeout: 15_000 });

  // In single-shot the finding statement is the answer.
  await expect(page.getByText(ANSWER)).toHaveCount(1);
});

test("polling stops once the run has finished", async ({ page }) => {
  await openConversation(page);
  await ask(page);
  await expect(page.getByText(ANSWER)).toBeVisible({ timeout: 15_000 });

  const settled = api.calls.filter((call) => call.includes("/runs/")).length;
  await page.waitForTimeout(3_000);

  // A page left open must not ask forever.
  expect(api.calls.filter((call) => call.includes("/runs/")).length).toBe(settled);
});

test("the trace shows how the answer was worked out", async ({ page }) => {
  await openConversation(page);
  await ask(page);
  await expect(page.getByText(ANSWER)).toBeVisible({ timeout: 15_000 });

  // Collapsed once the run is over — the answer is the point then — but still there.
  const toggle = page.getByRole("button", { name: /Thought(\s+for\s+\d+\s+\w+)?$/ });
  await expect(toggle).toBeVisible();
  await toggle.click();

  await expect(page.getByText("Searched the catalogue for tables that fit the question")).toBeVisible();
  await expect(page.getByText("Decided what to look up")).toBeVisible();
  await expect(page.getByText("Ran the query against your database")).toBeVisible();
  // The machine name never reaches a person.
  await expect(page.getByText("query_executed")).toHaveCount(0);
});

test("a refresh mid-run replays the whole trace", async ({ page }) => {
  /** The M8 gate's own criterion. The trace is not held in the page. */
  await openConversation(page);
  await ask(page);
  await expect(page.getByText(ANSWER)).toBeVisible({ timeout: 15_000 });

  await page.reload();

  await expect(page.getByText(ANSWER)).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: /Thought(\s+for\s+\d+\s+\w+)?$/ }).click();
  await expect(page.getByText("Searched the catalogue for tables that fit the question")).toBeVisible();
  await expect(page.getByText("Finished")).toBeVisible();
});


test("the chart is drawn in the browser, inside the answer", async ({ page }) => {
  /** The half of WP11.1 that only a real browser can prove. jsdom has no canvas. */
  await openConversation(page);
  await ask(page);
  await expect(page.getByText(ANSWER)).toBeVisible({ timeout: 15_000 });

  const chart = page.getByTestId("chart");
  await expect(chart).toBeVisible({ timeout: 15_000 });
  // ECharts draws the figure as SVG.
  await expect(chart.locator("svg")).toBeVisible({ timeout: 15_000 });
  await expect(chart.locator("svg path")).not.toHaveCount(0);

  // And it is inside the run's own answer, not in a panel of its own — B-048.
  const answer = page.getByTestId("chart").locator("xpath=ancestor::*[@data-testid='answer'][1]");
  await expect(answer.getByText("Evidence", { exact: true })).toBeVisible();
});

test("the chart spec opens, the way the query does", async ({ page }) => {
  /** B-048: a chart nobody can trace back to what produced it is decoration that looks like... */
  await openConversation(page);
  await ask(page);
  await expect(page.getByText(ANSWER)).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: "Chart spec" }).click();

  await expect(page.getByText(`"mark": "${CHART_SPEC.mark}"`)).toBeVisible();
  // The values travel inline, and a reader can see that for themselves.
  await expect(page.getByText(/"order_count": 4125/)).toBeVisible();
});


test("drawing the chart reaches nothing outside the page", async ({ page }) => {
  /** The security claim of the whole chart design, in a real browser. */
  const offPage: string[] = [];
  const origin = new URL(page.url() || "http://localhost").origin;
  page.on("request", (request) => {
    const target = new URL(request.url());
    const own = target.host.includes("localhost") || target.host.includes("127.0.0.1");
    if (!own) offPage.push(request.url());
  });

  await openConversation(page);
  await ask(page);
  await expect(page.getByTestId("chart").locator("svg")).toBeVisible({ timeout: 15_000 });

  expect(offPage, `the page fetched something off ${origin}: ${offPage.join(", ")}`).toEqual([]);
});
