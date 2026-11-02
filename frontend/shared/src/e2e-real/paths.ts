import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Repository paths for the real-mode screen tests (P12.4). This module
// uses only node builtins so both runners can load it: the Playwright
// journeys and the vitest regression below.
const here = dirname(fileURLToPath(import.meta.url));
// shared/src/e2e-real -> shared/src -> shared -> frontend -> repo root.
const REPO = join(here, "..", "..", "..", "..");

export function dumpPath(): string {
  return join(REPO, "backend", "tests", "replays", "e2e-db.dump");
}

export function recordingsPath(): string {
  return join(REPO, "backend", "tests", "replays", "e2e-journeys.ready");
}

// The journeys need the throwaway database; the AI ones also need the
// saved replies from a --record run (P12.4 Task 6, needs your yes).
export function recordingsReady(): boolean {
  return existsSync(recordingsPath()) || process.env.E2E_RECORDING === "1";
}
