import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { dumpPath, recordingsPath } from "./paths";

// The journeys resolve these at collection time: a wrong root silently
// skips everything even when the dump and recordings are in place.
describe("real-mode paths", () => {
  test("point at the repository backend, not under frontend", () => {
    const repo = join(
      dirname(fileURLToPath(import.meta.url)),
      "..",
      "..",
      "..",
      "..",
    );
    expect(relative(repo, dumpPath())).toBe(
      join("backend", "tests", "replays", "e2e-db.dump"),
    );
    expect(relative(repo, recordingsPath())).toBe(
      join("backend", "tests", "replays", "e2e-journeys.ready"),
    );
  });
});
