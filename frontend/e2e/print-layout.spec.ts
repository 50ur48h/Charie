import { expect, test } from "@playwright/test";
import { CHAT, signedIn } from "./apps";

// P03.8 print regression: a long chat prints full-width and unclipped across
// pages, with on-screen controls (answer actions, block tools including
// "Download as image", thinking timeline) hidden and print-only evidence shown.
test("print layout is full-width, unclipped, and hides controls", async ({
  page,
}) => {
  await signedIn(page, CHAT, "/chat/1");
  await expect(page.locator(".answer-actions").first()).toBeVisible();
  await page.emulateMedia({ media: "print" });

  const facts = await page.evaluate(() => {
    const cs = (el: Element | null, prop: string) =>
      el ? getComputedStyle(el).getPropertyValue(prop) : "MISSING";
    const scroller = document.querySelector('[data-testid="messages"]');
    const wrap = scroller?.querySelector(":scope > div") ?? null;
    const hidden = (sel: string) =>
      [...document.querySelectorAll(sel)].every(
        (el) => getComputedStyle(el).getPropertyValue("display") === "none",
      );
    const buttons = [...document.querySelectorAll("button")];
    return {
      noHorizontalOverflow:
        document.documentElement.scrollWidth <= window.innerWidth + 1,
      wrapMaxWidth: cs(wrap, "max-width"),
      wrapOverflowX: cs(wrap, "overflow-x"),
      scrollerOverflow: cs(scroller, "overflow-y"),
      scrollerHeight: cs(scroller, "height"),
      blockToolsHidden: hidden(".block-tools"),
      chartToolsHidden: hidden(".chart-tools"),
      actionsHidden: hidden(".answer-actions"),
      timelineHidden: hidden(".thinking-timeline"),
      dialogHidden: hidden(".wrong-dialog"),
      downloadControls: buttons
        .filter((b) =>
          (b.getAttribute("aria-label") ?? "").startsWith("Download as"),
        )
        .map((b) => b.textContent?.trim() ?? ""),
      methodPrintShown: (() => {
        const el = document.querySelector(".method-print");
        return !!el && getComputedStyle(el).getPropertyValue("display") !== "none";
      })(),
      multipage: document.body.scrollHeight > window.innerHeight,
    };
  });

  expect(facts.noHorizontalOverflow).toBe(true);
  expect(facts.wrapMaxWidth).toBe("none");
  expect([facts.wrapOverflowX, facts.scrollerOverflow]).toContain("visible");
  expect(facts.blockToolsHidden).toBe(true);
  expect(facts.chartToolsHidden).toBe(true);
  expect(facts.actionsHidden).toBe(true);
  expect(facts.timelineHidden).toBe(true);
  expect(facts.dialogHidden).toBe(true);
  expect(facts.methodPrintShown).toBe(true);
  expect(facts.multipage).toBe(true);

  // Every Download control (image and CSV) is effectively hidden in print,
  // including buttons whose own display stays set while an ancestor hides them.
  const downloads = page.getByRole("button", { name: /^Download as/ });
  expect(facts.downloadControls.length).toBeGreaterThan(0);
  for (const btn of await downloads.all()) await expect(btn).toBeHidden();
});
