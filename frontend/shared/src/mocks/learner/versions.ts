import type { KbVersion } from "../../api/learner-types";
import type { KnowledgeEntry } from "../../knowledge/types";
import { snapshotMockKnowledge } from "../sampleKnowledge";
import { learner, saveLearner } from "./state";

// Draft versions (mock only). A refresh run or an owner fix works on the
// open draft; with none, the first fix makes one from the live entries.

export function openDraft(): KbVersion | undefined {
  return learner().versions.find((version) => version.status === "draft");
}

export function liveVersion(): KbVersion | undefined {
  return learner().versions.find((version) => version.status === "published");
}

/** The published entries: the owner's save, or P03.11's samples. */
export function publishedBase(): KnowledgeEntry[] {
  return learner().publishedEntries ?? snapshotMockKnowledge();
}

/** The draft's working copy; null when there is no draft. */
export function draftWorkingCopy(): KnowledgeEntry[] | null {
  return learner().draftEntries;
}

export function changeCounts(versionNumber: number): { added: number; changed: number; removed: number } {
  const changes = learner().changesByVersion[versionNumber] ?? [];
  return {
    added: changes.filter((change) => change.change === "added").length,
    changed: changes.filter((change) => change.change === "changed").length,
    removed: changes.filter((change) => change.change === "removed").length,
  };
}

/** Make the open draft, or the live + 1 owner draft when there is none. */
export function ensureDraft(madeBy: KbVersion["made_by"], note: string): KbVersion {
  const store = learner();
  const existing = store.versions.find((version) => version.status === "draft");
  if (existing) return existing;
  const number = store.versions.reduce((max, version) => Math.max(max, version.number), 0) + 1;
  const draft: KbVersion = {
    id: store.versions.reduce((max, version) => Math.max(max, version.id), 0) + 1,
    number,
    status: "draft",
    made_by: madeBy,
    created_at: new Date().toISOString(),
    published_at: null,
    summary: { added: 0, changed: 0, removed: 0, note },
  };
  store.versions.unshift(draft);
  store.draftEntries = JSON.parse(JSON.stringify(publishedBase())) as KnowledgeEntry[];
  store.changesByVersion[number] = [];
  saveLearner();
  return draft;
}

const OWNER_FIX = "Changed by you.";
const OWNER_APPROVE = "Approved by you.";
const OWNER_REASONS = new Set([OWNER_FIX, OWNER_APPROVE]);

/** After an owner fix: the counts follow. A refresh draft keeps its note plus
 * " · {k} changes by you". New owner drafts stay "Your changes" (P04.8). */
export function touchDraftByOwner(versionNumber: number): void {
  const store = learner();
  const draft = store.versions.find((version) => version.number === versionNumber);
  if (!draft) return;
  if (draft.made_by === "owner_edit") {
    const counts = changeCounts(versionNumber);
    draft.summary.added = counts.added;
    draft.summary.changed = counts.changed;
    draft.summary.removed = counts.removed;
    saveLearner();
    return;
  }
  const counts = changeCounts(versionNumber);
  draft.summary.added = counts.added;
  draft.summary.changed = counts.changed;
  draft.summary.removed = counts.removed;
  const byYou = (store.changesByVersion[versionNumber] ?? []).filter((change) =>
    OWNER_REASONS.has(change.reason),
  ).length;
  const base = draft.summary.note.replace(/ · \d+ changes? by you$/, "");
  draft.summary.note =
    byYou === 0 ? base : `${base} · ${byYou === 1 ? "1 change" : `${byYou} changes`} by you`;
  saveLearner();
}

/** Apply an owner fix to one entry, creating its change. Returns the entry. */
export function applyOwnerFix(
  key: string,
  patch: { title?: string; meaning?: string },
  reason: string,
): KnowledgeEntry | undefined {
  const draft = ensureDraft("owner_edit", "Your changes");
  const store = learner();
  const working = store.draftEntries ?? [];
  const entry = working.find((e) => e.key === key);
  if (!entry) return undefined;
  if (patch.title !== undefined) entry.name = patch.title;
  if (patch.meaning !== undefined) entry.meaning = patch.meaning;
  entry.confidence = "owner";
  const changes = store.changesByVersion[draft.number] ?? [];
  const open = changes.find((change) => change.key === key);
  const base = publishedBase().find((e) => e.key === key) ?? null;
  if (open) {
    open.after = { ...entry };
    open.title = entry.name;
    open.reason = reason;
  } else {
    changes.push({
      key,
      title: entry.name,
      change: base === null ? "added" : "changed",
      before: base === null ? null : { ...base },
      after: { ...entry },
      reason,
      is_big: false,
    });
  }
  store.changesByVersion[draft.number] = changes;
  touchDraftByOwner(draft.number);
  return { ...entry };
}

/** Approve one entry: it is confirmed, and its open change says so. */
export function applyApprove(key: string): KnowledgeEntry | undefined {
  const draft = ensureDraft("owner_edit", "Your changes");
  const store = learner();
  const entry = (store.draftEntries ?? []).find((e) => e.key === key);
  if (!entry) return undefined;
  entry.confidence = "owner";
  const changes = store.changesByVersion[draft.number] ?? [];
  const open = changes.find((change) => change.key === key);
  const base = publishedBase().find((e) => e.key === key) ?? null;
  if (open) {
    open.after = { ...entry };
    open.title = entry.name;
    open.reason = OWNER_APPROVE;
  } else {
    changes.push({
      key,
      title: entry.name,
      change: base === null ? "added" : "changed",
      before: base === null ? null : { ...base },
      after: { ...entry },
      reason: OWNER_APPROVE,
      is_big: false,
    });
  }
  store.changesByVersion[draft.number] = changes;
  touchDraftByOwner(draft.number);
  return { ...entry };
}
