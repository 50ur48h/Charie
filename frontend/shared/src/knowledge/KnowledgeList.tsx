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
import type { KnowledgeEntry, KnowledgeKind } from "./types";

export const KNOWLEDGE_KINDS: { key: KnowledgeKind | "all"; label: string; icon: LucideIcon }[] = [
  { key: "all", label: "All", icon: Layers },
  { key: "number", label: "Business numbers", icon: Sigma },
  { key: "word", label: "Words & meanings", icon: MessageSquare },
  { key: "table", label: "Tables & columns", icon: Database },
  { key: "rule", label: "Rules", icon: ShieldCheck },
  { key: "code", label: "Codes", icon: Hash },
  { key: "event", label: "Events", icon: Calendar },
  { key: "problem", label: "Data problems", icon: CircleAlert },
];

export function kindLabel(kind: KnowledgeKind): string {
  return KNOWLEDGE_KINDS.find((k) => k.key === kind)?.label ?? kind;
}

export function kindIcon(kind: KnowledgeKind): LucideIcon {
  return KNOWLEDGE_KINDS.find((k) => k.key === kind)?.icon ?? Layers;
}

// The knowledge browser list: search, kind filters and entry rows.
// Selection is by stable key; the parent loads detail for the chosen key.
export function KnowledgeList({
  entries,
  counts,
  kind,
  query,
  selectedKey,
  onKindChange,
  onQueryChange,
  onSelect,
}: {
  entries: KnowledgeEntry[];
  counts: Record<string, number>;
  kind: KnowledgeKind | "all";
  query: string;
  selectedKey: string | null;
  onKindChange: (kind: KnowledgeKind | "all") => void;
  onQueryChange: (query: string) => void;
  onSelect: (key: string) => void;
}) {
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
      <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="Kinds">
        {KNOWLEDGE_KINDS.map(({ key, label, icon: Icon }) => {
          const active = kind === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onKindChange(key)}
              aria-pressed={active}
              className={
                active
                  ? "inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-[13px] font-semibold text-white [--icon:15px]"
                  : "inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-[13px] font-medium text-text-2 [--icon:15px]"
              }
            >
              <Icon aria-hidden="true" />
              {label}
              <span className={active ? undefined : "text-muted"}>{counts[key] ?? 0}</span>
            </button>
          );
        })}
      </div>
      {entries.length === 0 ? (
        <Card padded>
          <p className="text-[14px] text-muted">Nothing matches. Try another word.</p>
        </Card>
      ) : (
        <div className="grid gap-px" role="listbox" aria-label="Knowledge entries">
          {entries.map((entry) => {
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
                  <span className="block truncate text-[14px] font-medium">{entry.name}</span>
                  <span className="block truncate text-[12.5px] text-muted">{entry.short}</span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Confidence labels explain what the badge means without implying certainty.
export function ConfidencePill({ confidence }: { confidence: KnowledgeEntry["confidence"] }) {
  switch (confidence) {
    case "owner":
      return <Pill tone="good">Confirmed by you</Pill>;
    case "data":
      return <Pill tone="accent">Checked against data</Pill>;
    case "doc":
      return <Pill>From a document</Pill>;
    case "guess":
      return <Pill tone="warn">Guessed, needs checking</Pill>;
    case "conflict":
      return <Pill tone="bad">Documents disagree</Pill>;
  }
}
