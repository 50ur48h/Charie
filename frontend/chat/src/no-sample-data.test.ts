// P12.1: the chat app ships no sample data outside mock mode.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, test } from "vitest";

const ROOT = process.cwd();
const CHAT_SRC = resolve(ROOT, "chat", "src");
const SHARED_SRC = resolve(ROOT, "shared", "src");
const LEARNER_MAIN = resolve(ROOT, "learner", "src", "main.tsx");

function sources(root: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(root)) {
    // The dev-only kit gallery mounts only when DEV or VITE_MOCK (C084).
    if (name === "mocks" || name === "node_modules" || name === "__tests__" || name === "kit") continue;
    const path = join(root, name);
    if (statSync(path).isDirectory()) {
      out.push(...sources(path));
    } else if (/\.(ts|tsx)$/.test(name) && !/[.](test|spec)[.]/.test(name)) {
      out.push(path);
    }
  }
  return out;
}

describe("no-sample-data", () => {
  test("mocks load only in mock mode", () => {
    for (const entry of [join(CHAT_SRC, "main.tsx"), LEARNER_MAIN]) {
      const body = readFileSync(entry, "utf8");
      expect(body).toContain("VITE_MOCK");
      expect(body).toContain("await import(");
      expect(body).not.toMatch(/import\s+[^;]*\sfrom\s*["'][^"']*mocks["']/);
    }
    const offenders = sources(CHAT_SRC)
      .concat(sources(SHARED_SRC))
      .filter((path) => !path.endsWith("main.tsx"))
      .filter((path) => /["']([^"']*\/)?mocks["']/.test(readFileSync(path, "utf8")));
    expect(offenders).toEqual([]);
  });

  test("no sample names in the app's code", () => {
    const offenders: string[] = [];
    for (const path of sources(CHAT_SRC).concat(sources(SHARED_SRC))) {
      const body = readFileSync(path, "utf8");
      if (body.includes("Bella Forno") || body.includes("Sourabh") || body.includes("Downtown Austin")) {
        offenders.push(path);
      }
    }
    expect(offenders).toEqual([]);
  });
});
