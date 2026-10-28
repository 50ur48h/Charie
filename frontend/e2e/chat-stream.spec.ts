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
  await expect(page.getByText("I read this", { exact: false })).toBeVisible();
  await page.goto(`${CHAT}/`);
  await expect(page).toHaveURL(`${CHAT}/`);
  expect(await streamOpens(page)).toBe(1);
  expect(errors).toEqual([]);
});
