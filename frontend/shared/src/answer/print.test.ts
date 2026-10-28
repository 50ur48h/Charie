import { afterEach, describe, expect, test, vi } from "vitest";
import { printAnswer, waitForPrintReady } from "./print";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("printAnswer", () => {
  test("waits for readiness, prints with the chat title, then restores it", async () => {
    Object.defineProperty(document, "fonts", {
      configurable: true,
      value: { ready: Promise.resolve() },
    });
    const printSpy = vi.fn();
    Object.defineProperty(window, "print", { configurable: true, value: printSpy });
    const previous = document.title;

    await waitForPrintReady();
    const charts = document.querySelectorAll('[data-chart-container="true"]');
    expect(charts.length).toBe(0);

    await printAnswer("How are we doing this month?");
    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(document.title).toBe("How are we doing this month?");
    window.dispatchEvent(new Event("afterprint"));
    expect(document.title).toBe(previous);
  });
});
