import { designWorld, newWorld, type LearnerWorld } from "./data";

// Learner mock store (mock only): the fake server's memory for documents
// and runs. Saved to sessionStorage so a reload keeps changes; ?mock=new
// starts empty, ?mock=still is the design world with timers off, and no
// value is the design world. The value is read once at page load.
const STORE_KEY = "charie-learner-mock";

let world: LearnerWorld | null = null;

function storage(): Storage | null {
  try {
    return sessionStorage;
  } catch {
    return null;
  }
}

function load(): LearnerWorld | null {
  try {
    const raw = storage()?.getItem(STORE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as LearnerWorld;
    if (!Array.isArray(data?.documents) || !Array.isArray(data?.runs)) return null;
    return data;
  } catch {
    return null;
  }
}

export function saveLearner(): void {
  if (world === null) return;
  try {
    storage()?.setItem(STORE_KEY, JSON.stringify(world));
  } catch {
    // Test-only state; ignore.
  }
}

// Fresh worlds for tests. Pass "new" for the empty world, anything else
// (or nothing) for the design world.
export function resetLearnerMock(which: "design" | "new" = "design"): LearnerWorld {
  world = which === "new" ? newWorld() : designWorld();
  saveLearner();
  return world;
}

// The store, loading the saved world (or the design world) on first use.
export function learner(): LearnerWorld {
  if (world === null) world = load() ?? designWorld();
  return world;
}

// Read ?mock= once at page load and reset the store when it names a world;
// otherwise the store comes back from sessionStorage. Returns the mock
// value ("new", "still" or null) for timers and tests to read.
export function initLearnerWorld(search = ""): "new" | "still" | null {
  const query = search !== "" ? search : window.location.search;
  const mock = new URLSearchParams(query).get("mock");
  if (mock === "new" || mock === "still") {
    resetLearnerMock(mock === "new" ? "new" : "design");
    return mock;
  }
  return null;
}
