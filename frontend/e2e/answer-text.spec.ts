import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

test("prose blocks match the design: reading, text and follow-ups", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await expect(
    page.getByText("I read this as net sales, orders and average order", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText("We are ahead of September on every measure.")).toBeVisible();
  await expect(page.getByRole("button", { name: /How much did the outage cost us\?/ })).toBeVisible();
});

test("callout and suggestions render with verbatim confidence", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await expect(page.getByText("October has data up to the 26th only.")).toBeVisible();
  await expect(page.getByText("What I'd do")).toBeVisible();
  await expect(page.getByText("Ask the delivery partner to check Downtown.")).toBeVisible();
  await expect(page.getByText("· likely")).toBeVisible();
});

test("tone spans use the theme colors", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  const toned = page.getByText("up 6.2%", { exact: true });
  const marked = page.getByText("26th", { exact: true });
  const plain = page.getByText("We are ahead of September on every measure.");
  const tonedColor = await toned.evaluate((el) => getComputedStyle(el).color);
  const markedColor = await marked.evaluate((el) => getComputedStyle(el).color);
  const plainColor = await plain.evaluate((el) => getComputedStyle(el).color);
  expect(tonedColor).not.toBe(plainColor);
  expect(markedColor).not.toBe(plainColor);
});

test("a follow-up fills the composer", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  await page.getByRole("button", { name: /Same for last year\?/ }).click();
  await expect(page.getByRole("textbox", { name: "Ask a question" })).toHaveValue(
    "Same for last year?",
  );
});

test("the composer stays with a long answer", async ({ page }) => {
  await signedIn(page, CHAT, "/chat/1");
  const messages = page.getByTestId("messages");
  const composer = page.getByRole("textbox", { name: "Ask a question" });
  await messages.evaluate((el) => {
    el.scrollTop = 0;
  });
  await expect(composer).toBeInViewport();
  await messages.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await expect(composer).toBeInViewport();
});
