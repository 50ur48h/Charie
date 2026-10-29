import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";
import { initLearnerWorld } from "./learner/state";

export async function startMockApi(): Promise<void> {
  initLearnerWorld();
  const worker = setupWorker(...handlers);
  await worker.start({
    serviceWorker: { url: "/mockServiceWorker.js" },
    onUnhandledFrame: "bypass",
    quiet: true,
  });
}
