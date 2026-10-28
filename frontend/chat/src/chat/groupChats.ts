import type { ChatSummary } from "@charie/shared";

export type ChatGroupKind = "today" | "yesterday" | "previous7" | "older";

export interface ChatGroup {
  kind: ChatGroupKind;
  label: string;
  chats: ChatSummary[];
}

const GROUP_LABELS: Record<ChatGroupKind, string> = {
  today: "Today",
  yesterday: "Yesterday",
  previous7: "Previous 7 days",
  older: "Older",
};

const GROUP_ORDER: ChatGroupKind[] = ["today", "yesterday", "previous7", "older"];

// Calendar day (year/month/day) of an instant in the given time zone, so
// grouping follows the owner's wall clock across DST changes.
function dayParts(instant: number, timeZone: string): [number, number, number] {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(instant));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? NaN);
  return [get("year"), get("month"), get("day")];
}

// Whole calendar days between two dates, computed from UTC day numbers so
// DST transitions never shift a boundary.
function daysBetween(from: [number, number, number], to: [number, number, number]): number {
  return (
    Date.UTC(to[0], to[1] - 1, to[2]) / 86_400_000 -
    Date.UTC(from[0], from[1] - 1, from[2]) / 86_400_000
  );
}

function kindFor(ageInDays: number): ChatGroupKind {
  if (ageInDays <= 0) return "today";
  if (ageInDays === 1) return "yesterday";
  if (ageInDays <= 7) return "previous7";
  return "older";
}

// Groups chats by their updated day, newest first within each group.
// Future-dated chats (clock skew) land in Today rather than vanishing.
export function groupChats(
  chats: ChatSummary[],
  now: number = Date.now(),
  timeZone: string = Intl.DateTimeFormat().resolvedOptions().timeZone,
): ChatGroup[] {
  const today = dayParts(now, timeZone);
  const buckets = new Map<ChatGroupKind, ChatSummary[]>();
  for (const chat of chats) {
    const at = Date.parse(chat.updated_at);
    const age = Number.isNaN(at) ? 0 : daysBetween(dayParts(at, timeZone), today);
    const kind = kindFor(age);
    const bucket = buckets.get(kind);
    if (bucket) bucket.push(chat);
    else buckets.set(kind, [chat]);
  }
  return GROUP_ORDER.filter((kind) => buckets.has(kind)).map((kind) => ({
    kind,
    label: GROUP_LABELS[kind],
    chats: buckets.get(kind) ?? [],
  }));
}
