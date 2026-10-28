import { expect, test, type Page } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

async function ask(page: Page, text: string) {
  await page.getByRole("textbox", { name: "Ask a question" }).fill(text);
  await page.getByRole("button", { name: "Ask" }).click();
}

async function streamOpens(page: Page) {
  return page.evaluate(() => Number(localStorage.getItem("charie-mock-stream-opens") ?? "0"));
}

test("reconnect_mid_text replays missed events and completes once", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await page.evaluate(() =>
    localStorage.setItem("charie-mock-stream-fault", JSON.stringify({ dropAfter: 5 })),
  );
  await ask(page, "How are trucks doing?");
  // The saved structured answer replaces the streamed plain text, exactly
  // once: a doubled buffer or a lingering transient copy would both fail
  // this full-paragraph exact match.
  await expect(
    page.getByText(
      "I read this as How are trucks doing?. The numbers are in and October is ahead.",
      { exact: true },
    ),
  ).toBeVisible();
  expect(await streamOpens(page)).toBe(2);
});

test("error_then_done shows the message before the saved answer", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await page.evaluate(() =>
    localStorage.setItem(
      "charie-mock-stream-fault",
      JSON.stringify({ errorCode: "spending_paused", errorMessage: "Charie paused for now." }),
    ),
  );
  await ask(page, "How are trucks doing?");
  await expect(page.getByRole("alert")).toHaveText("Charie paused for now.");
  await expect(
    page.getByText(
      "I read this as How are trucks doing?. The numbers are in and October is ahead.",
      { exact: true },
    ),
  ).toBeVisible();
});

test("navigate_away aborts the stream without reconnects", async ({ page }) => {
  const errors: Error[] = [];
  page.on("pageerror", (error) => errors.push(error));
  await signedIn(page, CHAT, "/chat/1");
  await ask(page, "How are trucks doing?");
  // "Reading your question" is live-script-only (no seed uses it), so this
  // proves the stream itself is open before navigating away.
  await expect(page.getByText("Reading your question")).toBeVisible();
  await page.goto(`${CHAT}/`);
  await expect(page).toHaveURL(`${CHAT}/`);
  expect(await streamOpens(page)).toBe(1);
  expect(errors).toEqual([]);
});

test("new_chat streams the fresh answer", async ({ page }) => {
  const errors: Error[] = [];
  page.on("pageerror", (error) => errors.push(error));
  await signedIn(page, CHAT, "/");
  await ask(page, "How are new trucks doing?");
  await expect(page).toHaveURL(/\/chat\/\d+/);
  // The saved structured answer only exists once the stream completes, so
  // this exact match proves the fresh chat streamed exactly once.
  await expect(
    page.getByText(
      "I read this as How are new trucks doing?. The numbers are in and October is ahead.",
      { exact: true },
    ),
  ).toBeVisible();
  expect(await streamOpens(page)).toBe(1);
  expect(errors).toEqual([]);
});

test("reload resumes a running answer", async ({ page }) => {
  const errors: Error[] = [];
  page.on("pageerror", (error) => errors.push(error));
  await signedIn(page, CHAT, "/chat/1");
  await page.evaluate(() =>
    localStorage.setItem("charie-mock-stream-fault", JSON.stringify({ stallAfter: 5 })),
  );
  await ask(page, "How are trucks doing?");
  // The live panel line is script-only (no seed uses it): the first stream
  // is definitely open, so the reload aborts it mid-flight.
  await expect(page.getByText("Reading your question")).toBeVisible();
  await page.reload();
  // The resumed stream replays from scratch and completes once.
  await expect(
    page.getByText(
      "I read this as How are trucks doing?. The numbers are in and October is ahead.",
      { exact: true },
    ),
  ).toBeVisible();
  expect(await streamOpens(page)).toBe(2);
  expect(errors).toEqual([]);
});

test("sidebar switch aborts without reopening under the new chat", async ({ page }) => {
  const errors: Error[] = [];
  page.on("pageerror", (error) => errors.push(error));
  // Chat 3's seed is empty, so every marker below is genuinely live.
  await signedIn(page, CHAT, "/chat/3");
  await page.evaluate(() =>
    localStorage.setItem("charie-mock-stream-fault", JSON.stringify({ stallAfter: 5 })),
  );
  await ask(page, "How are trucks doing?");
  // Event 5 is in and the stall has fired (it runs synchronously at
  // enqueue): the open connection is mid-stream and can never complete.
  await expect(page.getByText("I read this", { exact: false })).toBeVisible();
  const menu = page.getByRole("button", { name: "Open menu" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: "How are we doing this month?" }).click();
  await expect(page).toHaveURL(`${CHAT}/chat/1`);
  // Past the old script's full length: no reopen, so the count holds and
  // the new chat shows its own saved answer, untouched by the old stream.
  await page.waitForTimeout(2500);
  expect(await streamOpens(page)).toBe(1);
  await expect(
    page.getByRole("heading", { name: "How are we doing this month?" }),
  ).toBeVisible();
  await expect(page.getByText("October is a good month so far", { exact: false })).toBeVisible();
  await expect(page.getByText("Reading your question")).toBeHidden();
  // Back on the emptied chat, its aborted answer resumes and completes once.
  // The sidebar list still shows the seed title: posting a message does not
  // refetch the chat list.
  const menuAgain = page.getByRole("button", { name: "Open menu" });
  if (await menuAgain.isVisible()) await menuAgain.click();
  await page.getByRole("link", { name: "Why did delivery drop in Austin?" }).click();
  await expect(page).toHaveURL(`${CHAT}/chat/3`);
  await expect(
    page.getByText(
      "I read this as How are trucks doing?. The numbers are in and October is ahead.",
      { exact: true },
    ),
  ).toBeVisible();
  expect(await streamOpens(page)).toBe(2);
  expect(errors).toEqual([]);
});
