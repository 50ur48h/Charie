import { expect, test } from "@playwright/test";
import { CHAT, LEARNER, SAMPLE_PASSWORD, signedIn } from "./apps";

test("a protected page sends you to the login page", async ({ page }) => {
  await page.goto(`${CHAT}/usage`);
  await expect(page).toHaveURL(`${CHAT}/login`);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByText("Sign in to Charie.")).toBeVisible();
});

test("a wrong password shows the message", async ({ page }) => {
  await page.goto(`${CHAT}/login`);
  await page.getByLabel("Password", { exact: true }).fill("not-the-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("That password didn't work. Try again.");
  await expect(page).toHaveURL(`${CHAT}/login`);
});

test("too many tries shows the wait message", async ({ page }) => {
  await page.goto(`${CHAT}/login`);
  const box = page.getByLabel("Password", { exact: true });
  const signIn = page.getByRole("button", { name: "Sign in", exact: true });
  for (let i = 0; i < 5; i += 1) {
    await box.fill("not-the-password");
    await signIn.click();
    await expect(page.getByRole("alert")).toHaveText("That password didn't work. Try again.");
  }
  await box.fill("not-the-password");
  await signIn.click();
  await expect(page.getByRole("alert")).toHaveText(
    "Too many tries. Please wait 5 minutes, then try again.",
  );
});

test("signing in takes you back to the page you wanted", async ({ page }) => {
  await page.goto(`${CHAT}/usage`);
  await expect(page).toHaveURL(`${CHAT}/login`);
  await page.getByLabel("Password", { exact: true }).fill(SAMPLE_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(`${CHAT}/usage`);
  await expect(page.getByRole("heading", { name: "Usage" })).toBeVisible();
});

test("the learner opens the setup guide after signing in", async ({ page }) => {
  await signedIn(page, LEARNER, "/setup");
  await expect(page).toHaveURL(`${LEARNER}/setup`);
  await expect(page.getByRole("heading", { name: "Set up Charie" })).toBeVisible();
});

test("you stay signed in after a reload", async ({ page }) => {
  await signedIn(page, CHAT, "/usage");
  await page.reload();
  await expect(page).toHaveURL(`${CHAT}/usage`);
  await expect(page.getByRole("heading", { name: "Usage" })).toBeVisible();
});

test("the eye button shows the password", async ({ page }) => {
  await page.goto(`${CHAT}/login`);
  const box = page.getByLabel("Password", { exact: true });
  await expect(box).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(box).toHaveAttribute("type", "text");
  await box.fill(SAMPLE_PASSWORD);
  await expect(box).toHaveValue(SAMPLE_PASSWORD);
});
