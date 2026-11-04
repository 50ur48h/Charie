/** The walk, in a browser, against the whole stack (plan WP11.2b). */

import { expect, test, type Page } from "@playwright/test";

/** Who signs in. */
const SUBJECT = "smoke";
const ORG = "Smoke";

/** How the API reaches the seeded database — a compose service name, not `localhost`. */
const SOURCE = {
  name: "Pizza demo",
  host: process.env.SMOKE_DB_HOST ?? "seed-pizza-pg",
  port: process.env.SMOKE_DB_PORT ?? "5432",
  database: process.env.SMOKE_DB_NAME ?? "pizza",
  username: process.env.SMOKE_DB_USER ?? "pizza_readonly",
  password: process.env.SMOKE_DB_PASSWORD ?? "",
};

/** The gate's count question. The scripted model does not read it. */
const QUESTION = "how many orders were placed in July 2026?";

/** What `llm/scripted.py` composes, verbatim. */
const SCRIPTED_ANSWER = "The scripted model answered from a fixed script.";

/** `ops/seed/truths.json` → `row_counts.orders`, held honest by `make check.truths`. */
const TOTAL_ORDERS = "71798";

/** Wait until the page is running, not merely served. */
async function running(page: Page) {
  await expect(page.getByText("Healthy")).toBeVisible({ timeout: 90_000 });
}

/** The organization this walk owns: created on the first run, reused after. */
async function organization(page: Page): Promise<void> {
  const chat = /\/orgs\/[0-9a-f-]{36}\/conversations$/;

  /** Wait for one of the two outcomes before deciding which happened. */
  await expect(
    page
      .getByRole("heading", { name: "Create an organization" })
      .or(page.getByRole("heading", { name: "What would you like to know?" }).first()),
  ).toBeVisible({ timeout: 60_000 });

  if (chat.test(page.url())) return;

  const listed = page.getByText(ORG, { exact: true });
  if ((await listed.count()) === 0) {
    await page.getByLabel("Name", { exact: true }).fill(ORG);
    await page.getByRole("button", { name: "Create" }).click();
  }
  await expect(listed).toBeVisible();

  // Onboarding now opens setup directly; verify that destination before chat.
  await page.getByRole("button", { name: "Set up", exact: true }).first().click();
  await page.waitForURL(/\/orgs\/[0-9a-f-]{36}\/settings$/, { timeout: 30_000 });
  await newChat(page);
  await page.waitForURL(chat, { timeout: 30_000 });
}

/** Into Settings, which is where every admin screen moved (WP13.1b). */
async function settings(page: Page): Promise<void> {
  await page.getByRole("link", { name: /Settings/ }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
}

/** Back to the chat, the way the sidebar offers it. */
async function newChat(page: Page): Promise<void> {
  await page.getByRole("link", { name: /New chat/ }).first().click();
  await page.waitForURL(/\/orgs\/[0-9a-f-]{36}\/conversations$/, { timeout: 30_000 });
}

test("the stack answers a question asked in a browser", async ({ page }) => {
  test.skip(
    !SOURCE.password,
    "SMOKE_DB_PASSWORD is unset. Run this through ops/scripts/web_smoke.sh, which brings up a stack whose model is scripted.",
  );

  // A browser console error is invisible in CI unless something prints it.
  page.on("pageerror", (error) => console.log(`  page error: ${error.message}`));
  page.on("requestfailed", (request) => {
    // An aborted request is this app working correctly.
    if (request.failure()?.errorText.includes("ERR_ABORTED")) return;
    console.log(`  request failed: ${request.method()} ${request.url()}`);
  });

  let conversation = "";

  await test.step("sign in, and land in the chat", async () => {
    await page.goto("/");
    await running(page);

    await page.getByLabel("Who are you").fill(SUBJECT);
    await page.getByRole("button", { name: "Continue" }).click();

    await organization(page);

    // The direction of WP13.1b, asserted rather than assumed.
    await expect(
      page.getByRole("heading", { name: "What would you like to know?" }).first(),
    ).toBeVisible({ timeout: 30_000 });
  });

  await test.step("register the seeded database, from Settings", async () => {
    // The admin screens moved behind Settings when the chat became the home.
    await settings(page);
    await page.getByRole("link", { name: "Data sources" }).click();
    await expect(page.getByRole("heading", { name: "Register a database" })).toBeVisible();

    if ((await page.getByRole("heading", { name: SOURCE.name }).count()) === 0) {
      // `exact`, because "Username" contains "Name".
      await page.getByLabel("Name", { exact: true }).fill(SOURCE.name);
      await page.getByLabel("Host").fill(SOURCE.host);
      await page.getByLabel("Port").fill(SOURCE.port);
      await page.getByLabel("Database").fill(SOURCE.database);
      await page.getByLabel("Username").fill(SOURCE.username);
      await page.getByLabel("Password", { exact: true }).fill(SOURCE.password);
      await page.getByRole("button", { name: "Register" }).click();
    }
    await expect(page.getByRole("heading", { name: SOURCE.name })).toBeVisible();
  });

  await test.step("prove the credentials cannot write", async () => {
    // Not politeness and not skippable: until this has passed.
    await page.getByRole("button", { name: "Test connection" }).click();
    // The panel's own three facts, not the badge: "reachable" is not "read-only".
    await expect(page.getByText("proven", { exact: true })).toBeVisible();
  });

  await test.step("read and profile the schema", async () => {
    // Both report what they found in the API's own words.
    await page.getByRole("button", { name: "Refresh catalog" }).click();
    await expect(page.getByText(/table\(s\)/)).toBeVisible();
    await page.getByRole("button", { name: "Profile columns" }).click();
    await expect(page.getByText(/Profiled \d+ column\(s\)/)).toBeVisible();
  });

  await test.step("choose the database this organization answers from", async () => {
    /** D-045's control, exercised where it matters. */
    // Idempotent, like the registration step above and for the same reason.
    const badge = page.getByText("Answers questions");
    if ((await badge.count()) === 0) {
      await page.getByRole("button", { name: "Answer questions from this" }).click();
    }
    await expect(badge).toBeVisible();
  });

  await test.step("ask from the chat, which creates the thread", async () => {
    /** The walk this work package exists to make possible. */
    await settings(page);
    await newChat(page);

    const box = page.getByLabel("Your question");
    await expect(box).toBeEnabled({ timeout: 30_000 });
    await expect(page.getByText(SOURCE.name)).toBeVisible();

    await box.fill(QUESTION);
    await page.getByRole("button", { name: "Send" }).click();

    await page.waitForURL(/\/conversations\/[0-9a-f-]{36}$/, { timeout: 30_000 });
    conversation = page.url();
  });

  await test.step("wait for the answer card", async () => {
    // The run is accepted before it finishes, and the screen has to notice it finish by itself.
    await expect(page.getByTestId("answer-text")).toHaveText(SCRIPTED_ANSWER, {
      timeout: 120_000,
    });
    // `exact`, because the shell wraps the card in further elements and a substring match now...
    await expect(page.getByText("answered", { exact: true })).toBeVisible();
  });

  await test.step("open the query behind the answer", async () => {
    // The working is folded away now (D-047), so the query is reached by opening Evidence.
    await page.getByText("Evidence", { exact: true }).first().click();

    await expect(page.getByText(/SELECT COUNT\(\*\)/i)).toBeVisible();
    // The database answered.
    await expect(
      page.getByRole("cell", { name: TOTAL_ORDERS, exact: true }),
      `the seeded database should have returned ${TOTAL_ORDERS} orders (ops/seed/truths.json)`,
    ).toBeVisible();
  });

  await test.step("open the trace", async () => {
    await page.getByRole("button", { name: /Thought(\s+for\s+\d+\s+\w+)?$/ }).first().click();

    await expect(page.getByText("Searched the catalogue for tables that fit the question")).toBeVisible();
    await expect(page.getByText("Decided what to look up")).toBeVisible();
    await expect(page.getByText("Ran the query against your database")).toBeVisible();
    await expect(page.getByText("Finished")).toBeVisible();
    // The machine name never reaches a person.
    await expect(page.getByText("query_executed")).toHaveCount(0);
  });

  await test.step("the first answer keeps its evidence when a second is asked", async () => {
    /** The gate walk's defect, in the place it was found (B-106). */
    await page.getByLabel("Ask a question").fill("and how many were cancelled?");
    await page.getByRole("button", { name: "Send" }).click();

    // Answer cards, not occurrences of the text.
    await expect(page.getByTestId("answer-text")).toHaveCount(2, { timeout: 120_000 });
    // Counted on the disclosures, not on the citation buttons.
    await expect(page.getByText("Evidence", { exact: true })).toHaveCount(2, { timeout: 60_000 });
    await expect(page.getByRole("button", { name: /Thought(\s+for\s+\d+\s+\w+)?$/ })).toHaveCount(2);
  });

  await test.step("a reload replays all of it from durable rows", async () => {
    // M8's criterion, and the cheapest possible check that the run was stored rather than held...
    await expect(async () => {
      await page.goto(conversation);
      await expect(page.getByRole("button", { name: "Continue" })).toHaveCount(0, {
        timeout: 30_000,
      });
    }).toPass({ timeout: 120_000 });

    // Both answers, and both sets of evidence.
    await expect(page.getByTestId("answer-text")).toHaveCount(2, { timeout: 30_000 });
    await expect(page.getByTestId("answer-text").first()).toHaveText(SCRIPTED_ANSWER);
    await expect(page.getByText("Evidence", { exact: true })).toHaveCount(2);
  });
});
