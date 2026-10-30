// Plain detail lines for one entry's Details section (P07.4).
// Numbers go through format.ts; lines with missing data are left out;
// kinds without details (metric onward) have none.
import { formatCount, formatDate, formatPercent, formatShortCount } from "../format";
import type { KnowledgeKind } from "./types";

function record(details: unknown): Record<string, unknown> {
  return typeof details === "object" && details !== null
    ? (details as Record<string, unknown>)
    : {};
}

function text(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function day(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const date = value.slice(0, 10);
  try {
    return formatDate(date);
  } catch {
    return null;
  }
}

function tableLines(details: unknown): string[] {
  const d = record(details);
  const lines: string[] = [d["is_view"] === true ? "View (a saved query)" : "Table"];
  const rows = num(d["row_estimate"]);
  if (rows !== null) lines.push(`About ${formatShortCount(rows)} rows`);
  if (Array.isArray(d["columns"])) {
    const count = d["columns"].length;
    lines.push(`${formatCount(count)} ${count === 1 ? "column" : "columns"}`);
  }
  const key = strings(d["primary_key"]).join(", ");
  if (key !== "") lines.push(`Key: ${key}`);
  const seen = num(d["rows_profiled"]);
  if (seen !== null) {
    lines.push(
      d["sampled"] === true
        ? `Looked at ${formatShortCount(seen)} rows (a sample)`
        : `Looked at all ${formatCount(seen)} rows`,
    );
  }
  const grain = text(d["grain"]);
  if (grain !== null) lines.push(`One row is: ${grain}`);
  return lines;
}

function columnLines(details: unknown): string[] {
  const d = record(details);
  const lines: string[] = [];
  const type = text(d["data_type"]);
  if (type !== null) lines.push(`Type: ${type}`);
  if (d["nullable"] === true) lines.push("Can be empty");
  if (d["nullable"] === false) lines.push("Never empty");
  const profile = record(d["profile"]);
  if (d["profile"] === null || d["profile"] === undefined) return lines;
  const emptyShare = num(profile["empty_share"]);
  if (emptyShare !== null) lines.push(`Empty: ${formatPercent(emptyShare * 100)}`);
  const distinct = num(profile["distinct"]);
  if (distinct !== null) lines.push(`Different values: ${formatShortCount(distinct)}`);
  if (profile["min"] !== null && profile["min"] !== undefined && profile["max"] !== null && profile["max"] !== undefined) {
    lines.push(`Smallest: ${String(profile["min"])} · Largest: ${String(profile["max"])}`);
  }
  const from = day(profile["date_from"]);
  const to = day(profile["date_to"]);
  if (from !== null && to !== null) lines.push(`Dates: ${from} to ${to}`);
  const pattern = text(profile["pattern"]);
  const patternShare = num(profile["pattern_share"]);
  if (pattern !== null) {
    lines.push(patternShare !== null ? `Pattern: ${pattern} (${formatPercent(patternShare * 100)} of values)` : `Pattern: ${pattern}`);
  }
  const top = Array.isArray(profile["top_values"]) ? profile["top_values"] : [];
  const counts = top.map((item) => num(record(item)["count"]) ?? 0);
  if (profile["strict"] === true || top.length === 0) {
    if (profile["strict"] === true) lines.push("Example values not kept (strict mode)");
  } else {
    const total = counts.reduce((sum, count) => sum + count, 0);
    const shown = top.map((item, index) => {
      const value = String(record(item)["value"] ?? "");
      const share = total > 0 ? formatPercent((counts[index] / total) * 100) : "?";
      return `${value} (${share})`;
    });
    lines.push(`Most common: ${shown.join(", ")}`);
  }
  const refersTo = text(d["refers_to"]);
  if (refersTo !== null) lines.push(`Points to ${refersTo}`);
  const unit = text(d["unit"]);
  if (unit !== null) lines.push(`Unit: ${unit}`);
  const currency = text(d["currency"]);
  if (currency !== null) lines.push(`Currency: ${currency}`);
  return lines;
}

function linkLines(details: unknown): string[] {
  const d = record(details);
  const lines: string[] = [];
  const fromTable = text(d["from_table"]);
  const toTable = text(d["to_table"]);
  if (fromTable !== null && toTable !== null) {
    const fromColumns = strings(d["from_columns"]).join(", ");
    const toColumns = strings(d["to_columns"]).join(", ");
    const from = fromColumns === "" ? fromTable : `${fromTable}.${fromColumns}`;
    const to = toColumns === "" ? toTable : `${toTable}.${toColumns}`;
    lines.push(`From ${from} to ${to}`);
  }
  if (d["cardinality"] === "one_to_one") {
    lines.push("Each row here matches at most one row there");
  } else if (d["cardinality"] === "many_to_one") {
    lines.push("Many rows here can point to the same row there");
  }
  const share = num(d["match_share"]);
  if (share !== null) lines.push(`Rows that match: ${formatPercent(share * 100)}`);
  if (d["found_by"] === "foreign_key") lines.push("Found from a foreign key");
  if (d["found_by"] === "matching_name") lines.push("Found from matching names");
  if (d["sampled"] === true) lines.push("Tested on a sample");
  return lines;
}

function rangeLines(details: unknown): string[] {
  const d = record(details);
  const lines: string[] = [];
  const from = day(d["date_from"]);
  const to = day(d["date_to"]);
  if (from !== null && to !== null) lines.push(`Dates from ${from} to ${to}`);
  const column = text(d["date_column"]);
  if (column !== null) lines.push(`Main date column: ${column}`);
  if (d["exact"] === false) lines.push("Measured on a sample");
  return lines;
}

function ruleLines(details: unknown): string[] {
  const d = record(details);
  const lines: string[] = [];
  const values = strings(d["values"]).join(", ");
  switch (d["rule_type"]) {
    case "never_use_table": {
      const table = text(d["table"]);
      if (table !== null) lines.push(`Never use the table ${table}`);
      break;
    }
    case "always_filter": {
      const column = text(d["column"]);
      if (column !== null && values !== "") lines.push(`Only rows where ${column} is ${values}`);
      break;
    }
    case "exclude_values": {
      const column = text(d["column"]);
      if (column !== null && values !== "") lines.push(`Leave out rows where ${column} is ${values}`);
      break;
    }
    case "currency": {
      const currency = text(d["currency"]);
      if (currency !== null) lines.push(`Money is in ${currency}`);
      break;
    }
    case "required_note": {
      const note = text(d["note_text"]);
      if (note !== null) lines.push(`Add this note: “${note}”`);
      break;
    }
  }
  return lines;
}

function styleLines(details: unknown): string[] {
  const topics = strings(record(details)["topics"]);
  return [topics.length > 0 ? `When: ${topics.join(", ")}` : "Always"];
}

function nameLines(details: unknown): string[] {
  const d = record(details);
  const items = Array.isArray(d["items"]) ? d["items"] : [];
  const table = text(d["table"]);
  const column = text(d["name_column"]);
  if (table === null || column === null) return [];
  const tail = d["truncated"] === true ? ", first 1,000 only" : "";
  return [`${formatCount(items.length)} names from ${table}.${column}${tail}`];
}

/** Plain lines for the Details section; other kinds have none. */
export function detailLines(kind: KnowledgeKind, details: unknown): string[] {
  switch (kind) {
    case "table":
      return tableLines(details);
    case "column":
      return columnLines(details);
    case "link":
      return linkLines(details);
    case "data_range":
      return rangeLines(details);
    case "rule":
      return ruleLines(details);
    case "style":
      return styleLines(details);
    case "name":
      return nameLines(details);
    default:
      return [];
  }
}
