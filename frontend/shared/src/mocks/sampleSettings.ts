import type { Settings } from "../api/settings";
import { isThemeKey } from "../theme/theme";

// Mock settings store (mock only). Defaults and validation mirror the real
// API (P05.5): the same keys, the same exact 400 messages, all-or-nothing
// saves. The budget-only helpers stay so the Usage dialog keeps working.
const SETTINGS_KEY = "charie-mock-settings";

const DEFAULTS: Settings = {
  theme: "sage",
  answer_length: "normal",
  number_format: "short",
  thinking_minutes: 10,
  show_reading: true,
  memory_on: true,
  spend_limit_usd: 150,
  spend_warn_percent: 80,
  time_zone: null,
  strict_mode: false,
  setup_done: true,
};

function storage(): Storage | null {
  try {
    return localStorage;
  } catch {
    return null;
  }
}

function readStored(): Partial<Settings> {
  try {
    const raw = storage()?.getItem(SETTINGS_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as Partial<Settings>;
  } catch {
    return {};
  }
}

export function getMockSettings(): Settings {
  const stored = readStored();
  return { ...DEFAULTS, ...stored };
}

const THEME_MESSAGE = "Theme must be one of: sage, lavender, mist, seafoam, mauve, slate.";

function check(key: string, value: unknown): string | null {
  switch (key) {
    case "theme":
      return value === "sage" ||
        value === "lavender" ||
        value === "mist" ||
        value === "seafoam" ||
        value === "mauve" ||
        value === "slate"
        ? null
        : THEME_MESSAGE;
    case "answer_length":
      return value === "short" || value === "normal" || value === "detailed"
        ? null
        : "Answer length must be short, normal or detailed.";
    case "number_format":
      return value === "short" || value === "full" ? null : "Number format must be short or full.";
    case "thinking_minutes":
      return Number.isInteger(value) && (value as number) >= 2 && (value as number) <= 15
        ? null
        : "Thinking time must be a whole number of minutes from 2 to 15.";
    case "show_reading":
    case "memory_on":
    case "strict_mode":
      return typeof value === "boolean" ? null : `\`${key}\` must be true or false.`;
    case "spend_limit_usd": {
      const limit = Number(value);
      return Number.isFinite(limit) && limit >= 0.01 && limit <= 100000
        ? null
        : "The monthly limit must be between $0.01 and $100,000.";
    }
    case "spend_warn_percent": {
      const warn = Number(value);
      return Number.isInteger(warn) && warn >= 1 && warn <= 99
        ? null
        : "The warning level must be a whole number from 1 to 99.";
    }
    case "time_zone":
      if (value === null) return null;
      if (typeof value !== "string" || value === "") return badZone(value);
      try {
        new Intl.DateTimeFormat("en-US", { timeZone: value });
        return null;
      } catch {
        return badZone(value);
      }
    default:
      return null;
  }
}

function badZone(value: unknown): string {
  return `Unknown time zone: \`${String(value)}\`. Use a name like Asia/Kolkata.`;
}

const REFUSED = new Set(["setup_done", "password_hash"]);
// password_hash never lives in the store, but refusing it (rather than
// calling it unknown) matches the real API's message.
const KNOWN = new Set([...Object.keys(DEFAULTS), "password_hash"]);

// Validate the whole patch first, then save everything (all-or-nothing).
export function updateMockSettings(patch: Record<string, unknown>): { ok: true } | { error: "bad_setting"; message: string } {
  for (const key of Object.keys(patch)) {
    if (REFUSED.has(key)) {
      return { error: "bad_setting", message: `This setting can't be changed here: \`${key}\`.` };
    }
    if (!KNOWN.has(key)) {
      return { error: "bad_setting", message: `Unknown setting: \`${key}\`.` };
    }
    const message = check(key, patch[key]);
    if (message !== null) return { error: "bad_setting", message };
  }
  const next = { ...readStored() };
  for (const [key, value] of Object.entries(patch)) {
    (next as Record<string, unknown>)[key] = key === "theme" && isThemeKey(value) ? value : value;
  }
  try {
    storage()?.setItem(SETTINGS_KEY, JSON.stringify(next));
  } catch {
    // Test-only state; ignore.
  }
  return { ok: true };
}

// Budget-only helpers for the Usage spending-limits dialog (same store).
export interface BudgetStore {
  spend_limit_usd: number;
  spend_warn_percent: number;
}

export function getMockBudgetSettings(): BudgetStore {
  const settings = getMockSettings();
  return { spend_limit_usd: settings.spend_limit_usd, spend_warn_percent: settings.spend_warn_percent };
}

export function updateMockBudgetSettings(patch: {
  spend_limit_usd?: unknown;
  spend_warn_percent?: unknown;
}): { ok: true } | { error: "bad_setting"; message: string } {
  const outcome = updateMockSettings({ ...patch });
  if ("error" in outcome) return outcome;
  return { ok: true };
}
