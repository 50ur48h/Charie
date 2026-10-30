import { designWorld, newWorld, type LearnerWorld } from "./data";
import type {
  DatabaseSource,
  OwnerNotes,
  Readiness,
  SetupState,
  SortedNotes,
} from "../../api/learner-types";
import { listMockQuestions } from "../sampleQuestions";

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
    if (!Array.isArray(data?.documents) || !Array.isArray(data?.runs) || !Array.isArray(data?.versions) || !Array.isArray(data?.todos)) return null;
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

// Fresh worlds for tests (setup slice included). Pass "new" for the empty
// world, anything else (or nothing) for the design world.
export function resetLearnerMock(which: "design" | "new" = "design"): LearnerWorld {
  world = which === "new" ? newWorld() : designWorld();
  saveLearner();
  setupSlice = which === "new" ? newSetup() : designSetup();
  saveSetup();
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
  // failed: the design world with the newest run stopped, timers off, so the
  // Learning page shows the retry path for a failed run.
  if (mock === "failed") {
    resetLearnerMock("design");
    const store = learner();
    const newest = [...store.runs].sort(
      (a, b) => Date.parse(b.started_at) - Date.parse(a.started_at),
    )[0];
    if (newest !== undefined && newest.status === "running") {
      newest.status = "failed";
      newest.finished_at = new Date().toISOString();
      newest.summary = "The database check stopped the run.";
      saveLearner();
    }
    return "still";
  }
  return null;
}

// Setup slice (mock only): the saved database connection (the password lives
// here, never in a response), the readiness report, the done flag, the owner
// notes. Knowledge versions live on the world, not here (P04.4's numbers are gone).
const SETUP_KEY = "charie-learner-setup";

export interface SetupSlice {
  source: DatabaseSource | null;
  password: string | null;
  readiness: Readiness | null;
  setupDone: boolean;
  notes: OwnerNotes;
}

const DESIGN_NOTES_TEXT = `# Notes for Charie
Bella Forno Group runs 24 restaurants in Texas.
## Hard rules
Money is always in US dollars. Never convert.
Never use the orders_old table.
Leave out test restaurants.
## Style
Start with the direct answer.
Use short paragraphs.
Add "unaudited figures" to profit answers.
## Hints about the data
Delivery fees are part of the order total.
Lunch means 11 am to 3 pm.
Austin restaurants share one delivery partner.
Our week starts on Monday.
Our finance year starts in January.
Ask me if anything is unclear.
Sourabh, 3 Oct 2026`;

const DESIGN_SORTED: SortedNotes = {
  hard_rules: [
    "Money is always in US dollars. Never convert.",
    "Never use the orders_old table.",
    "Leave out test restaurants.",
  ],
  style_rules: [
    "Start with the direct answer.",
    "Use short paragraphs.",
    'Add "unaudited figures" to profit answers.',
  ],
  data_hints: [
    "Delivery fees are part of the order total.",
    "Lunch means 11 am to 3 pm.",
    "Austin restaurants share one delivery partner.",
  ],
};

function designSetup(): SetupSlice {
  return {
    source: {
      kind: "postgres",
      name: "Bella Forno database",
      host: "bellaforno-db.postgres.database.azure.com",
      port: 5432,
      database: "bella_forno",
      username: "charie_readonly",
      status: "connected",
      read_only_ok: true,
      data_through: "2026-10-26",
      checked_at: "2026-10-27T19:30:00+05:30",
      details: { tables: 57, rows: 2400000 },
    },
    password: "demo-password",
    readiness: {
      numbers_checked: 41,
      numbers_total: 45,
      numbers_waiting: 4,
      practice_right: 183,
      practice_total: 200,
      weak_area: "Food waste",
      weak_area_why: "Few documents about it",
    },
    setupDone: false,
    notes: {
      text: DESIGN_NOTES_TEXT,
      saved_at: "2026-10-03T10:00:00+05:30",
      sorted: DESIGN_SORTED,
      sorted_at: "2026-10-03T10:00:00+05:30",
    },
  };
}

function newSetup(): SetupSlice {
  return {
    source: null,
    password: null,
    readiness: null,
    setupDone: false,
    notes: { text: "", saved_at: null, sorted: null, sorted_at: null },
  };
}

let setupSlice: SetupSlice | null = null;

function loadSetup(): SetupSlice | null {
  try {
    const raw = storage()?.getItem(SETUP_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as SetupSlice;
    if (!data || typeof data !== "object") return null;
    return data;
  } catch {
    return null;
  }
}

export function saveSetup(): void {
  if (setupSlice === null) return;
  try {
    storage()?.setItem(SETUP_KEY, JSON.stringify(setupSlice));
  } catch {
    // Test-only state; ignore.
  }
}

// The setup slice, loading the saved one (or the design one) on first use.
export function setup(): SetupSlice {
  if (setupSlice === null) setupSlice = loadSetup() ?? designSetup();
  return setupSlice;
}

// GET /api/setup: step is the first step that isn't complete.
export function setupState(): SetupState {
  const slice = setup();
  if (slice.setupDone) {
    return { setup_done: true, step: 5, readiness: slice.readiness };
  }
  const sourceOk = slice.source?.status === "connected";
  const docs = learner().documents.filter((doc) => doc.status !== "removed");
  const hasFirstRun = learner().runs.some((run) => run.kind === "first");
  const firstDone = learner().runs.some((run) => run.kind === "first" && run.status === "done");
  const notesSaved = slice.notes.text.trim() !== "";
  const waiting = listMockQuestions("waiting").length;
  let step = 5;
  if (!sourceOk) step = 1;
  else if (!hasFirstRun && docs.length === 0 && !notesSaved) step = 2;
  else if (!hasFirstRun || !firstDone) step = 3;
  else if (waiting > 0) step = 4;
  return { setup_done: false, step, readiness: slice.readiness };
}
