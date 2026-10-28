import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

const fontsStub = () => {
  const descriptor = Object.getOwnPropertyDescriptor(document, "fonts");
  return () => {
    if (descriptor) Object.defineProperty(document, "fonts", descriptor);
    else delete (document as unknown as Record<string, unknown>).fonts;
  };
};

let restoreFonts: (() => void) | null = null;

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  restoreFonts?.();
  restoreFonts = null;
  vi.useRealTimers();
});

function stubFontsReady(ready: Promise<void>): void {
  restoreFonts = fontsStub();
  Object.defineProperty(document, "fonts", { value: { ready }, configurable: true });
}

describe("fontsReady", () => {
  test("fontsReady waits for document.fonts.ready", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    stubFontsReady(gate);
    const { fontsReady } = await import("./fonts");
    let done = false;
    const pending = fontsReady().then(() => {
      done = true;
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(done).toBe(false);
    release();
    await pending;
    expect(done).toBe(true);
  });

  test("fontsReady stops waiting after 1.5 seconds", async () => {
    vi.useFakeTimers();
    try {
      stubFontsReady(new Promise<void>(() => {}));
      const { fontsReady } = await import("./fonts");
      let done = false;
      const pending = fontsReady().then(() => {
        done = true;
      });
      await vi.advanceTimersByTimeAsync(1499);
      expect(done).toBe(false);
      await vi.advanceTimersByTimeAsync(1);
      await pending;
      expect(done).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });
});
