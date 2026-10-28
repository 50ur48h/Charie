// Unit-test stand-in for the browser-only "msw/browser" entry.
// jsdom/Node cannot register a Service Worker, so any import of
// "msw/browser" resolves here under vitest (see vitest.config.ts).
// Calling it is a test bug: the real worker is covered by the
// mock-mode Playwright suite instead.
export function setupWorker(): never {
  throw new Error("MSW browser worker is unavailable in unit tests.");
}
