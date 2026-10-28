import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const DIST_DIRS = ["chat/dist", "learner/dist"];
const BANNED_TEXTS = ["__kit", "[MSW]", "mockServiceWorker"];

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) yield* walk(full);
    else yield full;
  }
}

let failures = 0;
for (const dist of DIST_DIRS) {
  for (const file of walk(fileURLToPath(new URL(`../${dist}`, import.meta.url)))) {
    const name = file.split(/[\\/]/).at(-1);
    if (name === "mockServiceWorker.js") {
      console.error(`Found 'mockServiceWorker.js' in ${file}. The kit page and the fake API must never be in a production build.`);
      failures += 1;
      continue;
    }
    let text;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    for (const banned of BANNED_TEXTS) {
      if (text.includes(banned)) {
        console.error(`Found '${banned}' in ${file}. The kit page and the fake API must never be in a production build.`);
        failures += 1;
      }
    }
  }
}

if (failures > 0) process.exit(1);
console.log("Production builds are clean: no kit page and no fake API.");
