import { useState } from "react";
import {
  Calendar,
  Database,
  Hash,
  Layers,
  MessageSquare,
  Search,
  ShieldCheck,
  Sigma,
  CircleAlert,
  type LucideIcon,
} from "lucide-react";
import { Card } from "../components/Card";
import { Input } from "../components/Input";
import { Pill } from "../components/Pill";
import { KIND_GROUPS, entryGroupLabel, type KnowledgeGroup } from "./groups";
import type { KnowledgeConfidence, KnowledgeEntry, KnowledgeKind } from "./types";

const GROUP_ICONS: Record<Exclude<KnowledgeGroup, "all">, LucideIcon> = {
  numbers: Sigma,
  words: MessageSquare,
  tables: Database,
  rules: ShieldCheck,
  codes: Hash,
  events: Calendar,
  problems: CircleAlert,
};

export function kindIcon(kind: KnowledgeKind): LucideIcon {
  const group = KIND_GROUPS.find((entry) => entry.kinds.includes(kind))?.key;
  return (group !== undefined ? GROUP_ICONS[group] : Layers) ?? Layers;
}

// The knowledge browser list: search, group filters and entry rows.
// Selection is by stable key; the parent loads detail for the chosen key.
// The learner's editable list adds "All" / "Needs review" tabs under the
// search (guessed entries and disagreements first). Counts and the review
// count cover the whole version; `entries` are already filtered on screen.
export function KnowledgeList({
  entries,
  counts,
  needsReview,
  group,
  query,
  selectedKey,
  editable = false,
  onGroupChange,
  onQueryChange,
  onSelect,
}: {
  entries: KnowledgeEntry[];
  counts: Record<KnowledgeGroup, number>;
  needsReview: number;
  group: KnowledgeGroup;
  query: string;
  selectedKey: string | null;
  editable?: boolean;
  onGroupChange: (group: KnowledgeGroup) => void;
  onQueryChange: (query: string) => void;
  onSelect: (key: string) => void;
}) {
  const [reviewOnly, setReviewOnly] = useState(false);
  const reviewEntries = entries.filter(
    (entry) => entry.confidence === "guessed" || entry.confidence === "conflicting",
  );
  const shown = reviewOnly ? reviewEntries : entries;
  return (
    <div>
      <div className="mb-3">
        <Input
          icon={Search}
          aria-label="Search everything Charie has learned"
          placeholder="Search everything Charie has learned"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
        />
      </div>
      {editable && (
        <div className="mb-3 flex gap-1.5" role="group" aria-label="Review filter">
          <button
            type="button"
            onClick={() => setReviewOnly(false)}
            aria-pressed={!reviewOnly}
            className={
              !reviewOnly
                ? "inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-[13px] font-semibold text-white"
                : "inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-[13px] font-medium text-text-2"
            }
          >
            All
          </button>
          <button
            type="button"
            onClick={() => setReviewOnly(true)}
            aria-pressed={reviewOnly}
            className={
              reviewOnly
                ? "inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-[13px] font-semibold text-white"
                : "inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-[13px] font-medium text-text-2"
            }
          >
            Needs review
            <span className={reviewOnly ? undefined : "text-muted"}>{needsReview}</span>
          </button>
        </div>
      )}
      <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="Kinds">
        <GroupButton
          active={group === "all"}
          label="All"
          icon={Layers}
          count={counts.all}
          onClick={() => onGroupChange("all")}
        />
        {KIND_GROUPS.map(({ key, label }) => (
          <GroupButton
            key={key}
            active={group === key}
            label={label}
            icon={GROUP_ICONS[key]}
            count={counts[key]}
            onClick={() => onGroupChange(key)}
          />
        ))}
      </div>
      {shown.length === 0 ? (
        <Card padded>
          <p className="text-[14px] text-muted">
            {reviewOnly ? "Nothing needs review right now." : "Nothing matches. Try another word."}
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-px" role="listbox" aria-label="Knowledge entries">
          {shown.map((entry) => {
            const Icon = kindIcon(entry.kind);
            const selected = entry.key === selectedKey;
            return (
              <button
                key={entry.key}
                type="button"
                role="option"
                aria-selected={selected}
                onClick={() => onSelect(entry.key)}
                className={
                  selected
                    ? "flex items-center gap-3 rounded-[10px] bg-surface px-3 py-2 text-left shadow-raised"
                    : "flex items-center gap-3 rounded-[10px] px-3 py-2 text-left hover:bg-[rgba(var(--shadow-rgb),.05)]"
                }
              >
                <span className="grid size-[30px] flex-none place-items-center rounded-lg bg-surface-2 text-text-2 [--icon:16px]">
                  <Icon aria-hidden="true" />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[14px] font-medium">{entry.title}</span>
                  <span className="block truncate text-[12.5px] text-muted">
                    {group === "all" ? `${entryGroupLabel(entry.kind)} · ${entry.meaning}` : entry.meaning}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function GroupButton({
  active,
  label,
  icon: Icon,
  count,
  onClick,
}: {
  active: boolean;
  label: string;
  icon: LucideIcon;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        active
          ? "inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-[13px] font-semibold text-white [--icon:15px]"
          : "inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-[13px] font-medium text-text-2 [--icon:15px]"
      }
    >
      <Icon aria-hidden="true" />
      {label}
      <span className={active ? undefined : "text-muted"}>{count}</span>
    </button>
  );
}

// Confidence labels explain what the badge means without implying certainty.
export function ConfidencePill({ confidence }: { confidence: KnowledgeConfidence }) {
  switch (confidence) {
    case "confirmed":
      return <Pill tone="good">Confirmed by you</Pill>;
    case "checked":
      return <Pill tone="accent">Checked against data</Pill>;
    case "from_document":
      return <Pill>From a document</Pill>;
    case "guessed":
      return <Pill tone="warn">Guessed, needs checking</Pill>;
    case "conflicting":
      return <Pill tone="bad">Documents disagree</Pill>;
  }
}
