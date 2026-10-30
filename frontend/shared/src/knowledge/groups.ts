// The 7 kind groups behind the Knowledge buttons (P07.4): Business
// numbers = metric, dimension; Words & meanings = default, calendar,
// name, how_to, example; Tables & columns = table, column, link,
// data_range; Rules = rule, style; Codes = code; Events = event;
// Data problems = data_problem.
import type { KnowledgeEntry, KnowledgeKind } from "./types";

export type KnowledgeGroup =
  | "all"
  | "numbers"
  | "words"
  | "tables"
  | "rules"
  | "codes"
  | "events"
  | "problems";

export const KIND_GROUPS: { key: Exclude<KnowledgeGroup, "all">; label: string; kinds: KnowledgeKind[] }[] = [
  { key: "numbers", label: "Business numbers", kinds: ["metric", "dimension"] },
  {
    key: "words",
    label: "Words & meanings",
    kinds: ["default", "calendar", "name", "how_to", "example"],
  },
  {
    key: "tables",
    label: "Tables & columns",
    kinds: ["table", "column", "link", "data_range"],
  },
  { key: "rules", label: "Rules", kinds: ["rule", "style"] },
  { key: "codes", label: "Codes", kinds: ["code"] },
  { key: "events", label: "Events", kinds: ["event"] },
  { key: "problems", label: "Data problems", kinds: ["data_problem"] },
];

export function groupLabel(group: KnowledgeGroup): string {
  if (group === "all") return "All";
  return KIND_GROUPS.find((entry) => entry.key === group)?.label ?? group;
}

/** The group button label shown on an entry row. */
export function entryGroupLabel(kind: KnowledgeKind): string {
  return groupLabel(KIND_GROUPS.find((entry) => entry.kinds.includes(kind))?.key ?? "all");
}

/** Whole-version counts per group, for the button badges. */
export function groupCounts(counts: Record<string, number>): Record<KnowledgeGroup, number> {
  const grouped: Record<KnowledgeGroup, number> = {
    all: 0,
    numbers: 0,
    words: 0,
    tables: 0,
    rules: 0,
    codes: 0,
    events: 0,
    problems: 0,
  };
  for (const group of KIND_GROUPS) {
    grouped[group.key] = group.kinds.reduce((sum, kind) => sum + (counts[kind] ?? 0), 0);
  }
  grouped.all = KIND_GROUPS.reduce((sum, group) => sum + grouped[group.key], 0);
  return grouped;
}

// The screens fetch the whole version once and filter on the screen
// (instant): keep the group, then keep every word of the search.
export function filterEntries(
  entries: KnowledgeEntry[],
  group: KnowledgeGroup,
  query: string,
): KnowledgeEntry[] {
  const words = query.toLowerCase().split(/\s+/).filter((word) => word.length > 0);
  const kinds =
    group === "all" ? null : (KIND_GROUPS.find((entry) => entry.key === group)?.kinds ?? []);
  return entries.filter((entry) => {
    if (kinds !== null && !kinds.includes(entry.kind)) return false;
    if (words.length === 0) return true;
    const haystack = `${entry.key} ${entry.title} ${entry.meaning}`.toLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}
