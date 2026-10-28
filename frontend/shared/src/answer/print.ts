// Print readiness for "Download as PDF" (P03.8). Printing waits for
// document fonts (charts draw after them) and for every chart container
// to report ready, so the PDF holds finished charts instead of blanks.
// Bounded: slow charts never block printing for more than a few seconds.
import { fontsReady } from "../theme/fonts";

const READY_TIMEOUT_MS = 3000;
const POLL_MS = 100;

function chartsPending(): boolean {
  if (typeof document === "undefined") return false;
  const charts = [...document.querySelectorAll('[data-chart-container="true"]')];
  return charts.some((chart) => chart.getAttribute("data-chart-ready") !== "true");
}

export async function waitForPrintReady(timeoutMs = READY_TIMEOUT_MS): Promise<void> {
  try {
    await fontsReady();
  } catch {
    // Fonts must never block printing.
  }
  const start = Date.now();
  while (chartsPending() && Date.now() - start < timeoutMs) {
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}

/**
 * Open the browser print window with the chat title as the document
 * title, so "Save as PDF" names the file after the chat. Restores the
 * previous title afterwards, so repeated printing leaves no trace.
 */
export async function printAnswer(title: string): Promise<void> {
  if (typeof document === "undefined" || typeof window.print !== "function") return;
  await waitForPrintReady();
  const previous = document.title;
  const restore = (): void => {
    document.title = previous;
    window.removeEventListener("afterprint", restore);
  };
  document.title = title;
  window.addEventListener("afterprint", restore);
  window.print();
  // afterprint does not fire when the dialog is dismissed in some
  // browsers: restore on a delay as well.
  window.setTimeout(() => {
    if (document.title === title) restore();
  }, 1000);
}
