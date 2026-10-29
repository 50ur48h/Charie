import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";
import { initLearnerWorld } from "./learner/state";
import { startLearnerMockTimers } from "./learner/timers";

export async function startMockApi(): Promise<void> {
  // The reader and run clocks (P04.5, P04.7). Never for ?mock=still,
  // and never in Vitest (tests call the ticks directly).
  const timerWorld = initLearnerWorld();
  if (timerWorld !== "still") startLearnerMockTimers();
  const worker = setupWorker(...handlers);
  await worker.start({
    serviceWorker: { url: "/mockServiceWorker.js" },
    onUnhandledFrame: "bypass",
    quiet: true,
  });
}
