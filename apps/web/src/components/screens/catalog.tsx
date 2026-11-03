"use client";

/**
 * What we know about one database, and who may see it (plan WP4.3).
 *
 * Three things this screen refuses to blur together, because the product's
 * honesty depends on the distinction:
 *
 *   1. **Suspected is not decided.** The classifier's opinion and an Admin's
 *      decision are shown as separate facts. A column reading "masked" with
 *      "nobody has reviewed this" beside it is the truth; a single green tick
 *      would be a claim nobody made.
 *   2. **Masked is not absent.** A masked column is listed like any other, with
 *      its type and its role, because somebody asking "can I group by this"
 *      needs an answer even when they may not see the values.
 *   3. **A sample is a sample.** Counts say how many rows they came from, so
 *      "12% empty" is never mistaken for a statement about the whole table.
 *
 * The card is shown verbatim. It is the text the agent will be given, and a
 * person who wants to know why the agent answered oddly should be able to read
 * exactly what it read.
 */

import {
  createColumnHelper,
  createSortedRowModel,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_text,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpDown,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  FileText,
  ListFilter,
  Lock,
  Search,
  Table2,
} from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { controlClass } from "@/components/ui/input";
import { SkeletonList } from "@/components/ui/skeleton";
import {
  createApi,
  type CardHit,
  type Catalog,
  type CatalogColumn,
  type CatalogTable,
} from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

const POLICIES = ["allow", "mask", "deny"] as const;

const SENSITIVITY_TONES: Record<string, Tone> = {
  suspected: "peach",
  confirmed: "rose",
};

const POLICY_TONES: Record<string, Tone> = {
  allow: "mint",
  mask: "peach",
  deny: "rose",
};

/** The same tones as the policy badge, for the select an Admin decides with. */
const POLICY_FILLS: Record<string, string> = {
  allow: "bg-good-soft text-good-ink",
  mask: "bg-warn-soft text-warn-ink",
  deny: "bg-bad-soft text-bad-ink",
};

/** Least to most withheld, so sorting by policy gathers what is hidden. */
const POLICY_ORDER: Record<string, number> = { allow: 0, mask: 1, deny: 2 };

/** With this many tables or fewer, every one opens on arrival. */
const OPEN_BY_DEFAULT = 3;

function percentage(value: number | null): string | null {
  if (value === null) return null;
  return `${Math.round(value * 100)}% empty`;
}

function facts(column: CatalogColumn): string[] {
  const found: string[] = [];
  const empty = percentage(column.null_frac);
  if (empty && column.null_frac !== null && column.null_frac > 0) found.push(empty);
  if (column.distinct_est !== null) found.push(`${column.distinct_est} distinct`);
  if (column.min_val !== null && column.max_val !== null) {
    found.push(`${column.min_val} … ${column.max_val}`);
  }
  if (column.sample_rows !== null) found.push(`from ${column.sample_rows} sampled rows`);
  return found;
}

function qualified(table: { schema_name: string; table_name: string }): string {
  return `${table.schema_name}.${table.table_name}`;
}

/** A stable element id for a table's row, so a search hit can scroll to it. */
function anchorOf(name: string): string {
  return `catalog-table-${name.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

// ---------------------------------------------------------------------------
// The columns of one table, as a sortable TanStack table
// ---------------------------------------------------------------------------

/**
 * What a policy cell needs from the screen. Carried by context so the column
 * definitions below can live at module scope and stay stable between renders.
 */
const PolicyControls = createContext<{
  canDecide: boolean;
  busy: boolean;
  onDecide: (columnId: string, policy: string) => void;
}>({ canDecide: false, busy: false, onDecide: () => undefined });

function ColumnCell({ column }: { column: CatalogColumn }) {
  return (
    <div className="min-w-[180px]">
      <div className="font-mono text-[13px] font-medium text-text">{column.name}</div>
      <div className="mt-0.5 text-[12px] text-muted-foreground">
        {column.data_type}
        {column.is_pk ? " · primary key" : ""}
        {column.nullable ? "" : " · required"}
      </div>
      {column.description && (
        <div className="mt-1 max-w-[44ch] text-[12.5px] leading-relaxed text-text-2">
          {column.description}
        </div>
      )}
    </div>
  );
}

function RoleCell({ column }: { column: CatalogColumn }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {column.semantic_role && <Badge tone="sky">{column.semantic_role}</Badge>}
      {column.sensitivity !== "none" && (
        <Badge tone={SENSITIVITY_TONES[column.sensitivity] ?? "neutral"}>
          {column.sensitivity}
        </Badge>
      )}
    </div>
  );
}

function SampleCell({ column }: { column: CatalogColumn }) {
  return (
    <div className="max-w-[38ch] min-w-[160px] text-[12.5px] leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">
      {facts(column).join(" · ") || "not profiled"}
    </div>
  );
}

function PolicyCell({ column }: { column: CatalogColumn }) {
  const { canDecide, busy, onDecide } = useContext(PolicyControls);
  const id = useId();
  const fill = POLICY_FILLS[column.policy] ?? "bg-surface-2 text-text-2";
  return (
    <div className="grid min-w-[150px] justify-items-start gap-1">
      {canDecide ? (
        <>
          <label className="sr-only" htmlFor={id}>
            Change policy
          </label>
          <span className={cn("relative inline-flex rounded-full", fill)}>
            <select
              id={id}
              className="h-7 cursor-pointer appearance-none rounded-full bg-transparent py-0 pr-7 pl-2.5 text-[12px] font-semibold text-inherit outline-none focus-visible:ring-[3px] focus-visible:ring-focus disabled:cursor-not-allowed disabled:opacity-60"
              value={column.policy}
              disabled={busy}
              onChange={(event) => onDecide(column.id, event.target.value)}
            >
              {POLICIES.map((policy) => (
                <option key={policy} value={policy}>
                  {policy}
                </option>
              ))}
            </select>
            <ChevronDown
              aria-hidden="true"
              className="pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2"
            />
          </span>
        </>
      ) : (
        <Badge tone={POLICY_TONES[column.policy] ?? "neutral"}>{column.policy}</Badge>
      )}
      {/* Whether a person decided is a different fact from what was decided,
          and the screen says both rather than implying review that never
          happened. */}
      <span className="text-[12px] text-muted-foreground">
        {column.policy_decided ? "decided by an admin" : "nobody has reviewed this"}
      </span>
    </div>
  );
}

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric, text: sortFn_text },
});

const columnHelper = createColumnHelper<typeof features, CatalogColumn>();

const COLUMNS = columnHelper.columns([
  columnHelper.accessor("name", {
    header: "Column",
    sortFn: "alphanumeric",
    cell: (info) => <ColumnCell column={info.row.original} />,
  }),
  columnHelper.accessor((entry) => entry.semantic_role ?? "", {
    id: "role",
    header: "Role",
    sortFn: "text",
    cell: (info) => <RoleCell column={info.row.original} />,
  }),
  columnHelper.display({
    id: "sample",
    header: "Sample",
    cell: (info) => <SampleCell column={info.row.original} />,
  }),
  columnHelper.accessor((entry) => POLICY_ORDER[entry.policy] ?? POLICIES.length, {
    id: "policy",
    header: "Policy",
    cell: (info) => <PolicyCell column={info.row.original} />,
  }),
]);

function ColumnsTable({ columns }: { columns: CatalogColumn[] }) {
  const table = useTable({
    features,
    columns: COLUMNS,
    data: columns,
    getRowId: (row) => row.id,
  });

  return (
    <div className="overflow-x-auto rounded-md border border-border-soft bg-surface">
      <table className="w-full border-collapse text-[13.5px]">
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => {
                const sorted = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={
                      sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined
                    }
                    className="border-b border-border bg-surface-2/50 px-3 py-2 text-left align-bottom text-[12px] font-semibold whitespace-nowrap text-muted-foreground first:pl-4"
                  >
                    {header.isPlaceholder ? null : header.column.getCanSort() ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className={cn(
                          "-mx-1.5 inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 transition-colors hover:bg-surface-2 hover:text-text",
                          sorted && "text-text",
                        )}
                      >
                        <table.FlexRender header={header} />
                        {sorted === "asc" ? (
                          <ArrowUp aria-hidden="true" className="size-3.5" />
                        ) : sorted === "desc" ? (
                          <ArrowDown aria-hidden="true" className="size-3.5" />
                        ) : (
                          <ArrowUpDown aria-hidden="true" className="size-3.5 opacity-50" />
                        )}
                      </button>
                    ) : (
                      <table.FlexRender header={header} />
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className="border-b border-border-soft transition-colors last:border-b-0 hover:bg-surface-2/60"
            >
              {row.getAllCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2.5 align-top first:pl-4">
                  <table.FlexRender cell={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// One table in the list
// ---------------------------------------------------------------------------

function TableRow({
  table,
  open,
  onToggle,
  cardShown,
  onToggleCard,
}: {
  table: CatalogTable;
  open: boolean;
  onToggle: () => void;
  cardShown: boolean;
  onToggleCard: () => void;
}) {
  const name = qualified(table);
  const panel = `${anchorOf(name)}-columns`;
  const masked = table.columns.filter((entry) => entry.policy === "mask").length;
  const denied = table.columns.filter((entry) => entry.policy === "deny").length;

  return (
    <li id={anchorOf(name)} className="scroll-mt-6 border-b border-border-soft last:border-b-0">
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panel}
          onClick={onToggle}
          className="group -mx-2 grid w-[calc(100%+1rem)] grid-cols-[16px_minmax(0,1fr)] items-start gap-x-3 gap-y-1.5 rounded-md px-2 py-3 text-left transition-colors hover:bg-surface-2/60 sm:grid-cols-[16px_minmax(0,1fr)_auto]"
        >
          <ChevronRight
            aria-hidden="true"
            className={cn(
              "mt-[3px] size-4 shrink-0 text-muted-foreground transition-transform duration-200",
              open && "rotate-90 text-text",
            )}
          />
          <span className="min-w-0">
            <span className="block font-mono text-[13.5px] font-medium text-text [overflow-wrap:anywhere]">
              {name}
            </span>
            {table.description && (
              <span
                className={cn(
                  "mt-0.5 block text-[13px] leading-relaxed font-normal text-muted-foreground",
                  !open && "sm:truncate",
                )}
              >
                {table.description}
              </span>
            )}
          </span>
          <span className="col-start-2 flex flex-wrap items-center gap-1.5 sm:col-start-3 sm:justify-end">
            {masked > 0 && <Badge tone="peach">{masked} masked</Badge>}
            {denied > 0 && <Badge tone="rose">{denied} denied</Badge>}
            <Badge tone="lilac">{table.kind}</Badge>
            <span className="text-[12px] font-normal whitespace-nowrap text-muted-foreground tabular-nums">
              {table.row_estimate !== null && (
                <>~{table.row_estimate.toLocaleString()} rows · </>
              )}
              {table.columns.length} {table.columns.length === 1 ? "column" : "columns"}
            </span>
          </span>
        </button>
      </h3>

      {open && (
        <div id={panel} className="grid animate-fade-up gap-3 pt-1 pb-5 sm:pl-7">
          <ColumnsTable columns={table.columns} />
          {table.card_text && (
            <div className="grid justify-items-start gap-2">
              <Button variant="ghost" size="sm" className="-ml-2.5" onClick={onToggleCard}>
                <FileText />
                {cardShown ? "Hide card" : "Show card"}
              </Button>
              {cardShown && (
                <pre className="w-full animate-fade-up overflow-x-auto rounded-md bg-code p-4 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap text-code-ink">
                  {table.card_text}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function CatalogBrowser({
  orgId,
  dataSourceId,
  role,
}: {
  orgId: string;
  dataSourceId: string;
  role: string | null;
}) {
  const session = useSession();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  const isAdmin = role === "admin";

  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CardHit[] | null>(null);
  const [shown, setShown] = useState<string | null>(null);
  //: Tables a person has opened or closed. Anything not in here follows the
  //: default, which opens every table only when there are a handful of them.
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  const [filter, setFilter] = useState("");

  const load = useCallback(async () => {
    setCatalog(await api.catalog(orgId, dataSourceId));
  }, [api, orgId, dataSourceId]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const next = await api.catalog(orgId, dataSourceId);
        if (active) setCatalog(next);
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load");
      }
    })();
    return () => {
      active = false;
    };
  }, [api, orgId, dataSourceId]);

  const run = useCallback(async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That did not work");
    } finally {
      setBusy(false);
    }
  }, []);

  const search = (event: React.FormEvent) => {
    event.preventDefault();
    void run(async () => {
      setHits(await api.searchCatalog(orgId, query, dataSourceId));
    });
  };

  const decide = useCallback(
    (columnId: string, policy: string) =>
      void run(async () => {
        await api.setColumnPolicy(orgId, dataSourceId, columnId, { policy });
        await load();
      }),
    [api, orgId, dataSourceId, load, run],
  );

  const controls = useMemo(
    () => ({ canDecide: isAdmin, busy, onDecide: decide }),
    [isAdmin, busy, decide],
  );

  const tables = useMemo(() => catalog?.tables ?? [], [catalog]);
  const openByDefault = tables.length <= OPEN_BY_DEFAULT;
  const isOpen = (name: string) => opened[name] ?? openByDefault;

  const needle = filter.trim().toLowerCase();
  const visible = useMemo(
    () => (needle ? tables.filter((table) => qualified(table).toLowerCase().includes(needle)) : tables),
    [tables, needle],
  );

  const totals = useMemo(() => {
    const columns = tables.flatMap((table) => table.columns);
    return {
      columns: columns.length,
      masked: columns.filter((entry) => entry.policy === "mask").length,
      denied: columns.filter((entry) => entry.policy === "deny").length,
    };
  }, [tables]);

  const known = useMemo(() => new Set(tables.map(qualified)), [tables]);

  /** Opens a table a search found, and brings it into view. */
  const reveal = (name: string) => {
    setFilter("");
    setOpened((current) => ({ ...current, [name]: true }));
    requestAnimationFrame(() =>
      document.getElementById(anchorOf(name))?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  const allOpen = tables.length > 0 && tables.every((table) => isOpen(qualified(table)));
  const setAll = (open: boolean) =>
    setOpened(Object.fromEntries(tables.map((table) => [qualified(table), open])));

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      <Card
        title="Find a table"
        subtitle="Describe what you are looking for. Cards are searched, not just names."
      >
        <form onSubmit={search} className="flex flex-col gap-2.5 sm:flex-row">
          <div className="relative min-w-0 flex-1">
            <label className="sr-only" htmlFor="catalog-search">
              Search
            </label>
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <input
              id="catalog-search"
              type="search"
              className={cn(controlClass, "pl-9")}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="revenue"
            />
          </div>
          <Button
            variant="primary"
            type="submit"
            className="h-10 sm:px-5"
            disabled={busy || !query.trim()}
          >
            Search
          </Button>
        </form>

        {hits !== null && hits.length === 0 && (
          <p className="mt-4 animate-fade-up text-[13.5px] text-muted-foreground">
            Nothing matched. Try fewer words.
          </p>
        )}
        {hits !== null && hits.length > 0 && (
          <ul className="mt-4 grid gap-2">
            {hits.map((hit, index) => {
              const name = qualified(hit);
              const reachable = known.has(name);
              return (
                <li
                  key={name}
                  className="animate-fade-up rounded-md bg-surface-2/70 px-4 py-3"
                  style={{ animationDelay: `${index * 40}ms` }}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <Table2 aria-hidden="true" className="size-4 shrink-0 text-brand-ink" />
                      <span className="font-mono text-[13.5px] font-medium text-text [overflow-wrap:anywhere]">
                        {name}
                      </span>
                    </div>
                    {reachable && (
                      <Button variant="ghost" size="sm" className="-mr-2" onClick={() => reveal(name)}>
                        Open table
                        <ArrowRight />
                      </Button>
                    )}
                  </div>
                  <div className="mt-1.5 line-clamp-3 text-[13px] leading-relaxed whitespace-pre-line text-muted-foreground">
                    {hit.card_text}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card
        title="Tables"
        subtitle={
          catalog
            ? `Catalog version ${catalog.snapshot.version}, ${catalog.snapshot.object_count} table(s).`
            : undefined
        }
        action={
          tables.length > OPEN_BY_DEFAULT ? (
            <Button variant="ghost" size="sm" onClick={() => setAll(!allOpen)}>
              {allOpen ? "Collapse all" : "Expand all"}
            </Button>
          ) : undefined
        }
      >
        {error && (
          <div className="mb-4 flex animate-fade-up items-start gap-3 rounded-md bg-bad-soft px-4 py-3 text-[13.5px] text-bad-ink">
            <CircleAlert aria-hidden="true" className="mt-[3px] size-4 shrink-0" />
            <p role="alert" className="min-w-0 [overflow-wrap:anywhere]">
              {error}
            </p>
          </div>
        )}

        {catalog === null && !error && <SkeletonList rows={4} label="Loading the catalog" />}

        {catalog && (
          <>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge>{totals.columns} columns</Badge>
                {totals.masked > 0 && <Badge tone="peach">{totals.masked} masked</Badge>}
                {totals.denied > 0 && <Badge tone="rose">{totals.denied} denied</Badge>}
              </div>
              {tables.length > OPEN_BY_DEFAULT && (
                <div className="relative w-full sm:w-64">
                  <label className="sr-only" htmlFor="catalog-filter">
                    Filter tables by name
                  </label>
                  <ListFilter
                    aria-hidden="true"
                    className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                  />
                  <input
                    id="catalog-filter"
                    type="search"
                    className={cn(controlClass, "h-9 pl-9 text-[13.5px]")}
                    value={filter}
                    onChange={(event) => setFilter(event.target.value)}
                    placeholder="Filter by name"
                  />
                </div>
              )}
            </div>

            {!isAdmin && (
              <p className="mb-2 flex items-center gap-2 text-[13px] text-muted-foreground">
                <Lock aria-hidden="true" className="size-3.5 shrink-0" />
                Only an Admin can change what may be seen.
              </p>
            )}

            {visible.length === 0 && needle && (
              <p className="py-6 text-center text-[13.5px] text-muted-foreground">
                No table name contains &ldquo;{filter.trim()}&rdquo;.
              </p>
            )}

            <PolicyControls.Provider value={controls}>
              <ul className="border-t border-border-soft">
                {visible.map((table) => {
                  const name = qualified(table);
                  return (
                    <TableRow
                      key={name}
                      table={table}
                      open={isOpen(name)}
                      onToggle={() =>
                        setOpened((current) => ({ ...current, [name]: !isOpen(name) }))
                      }
                      cardShown={shown === name}
                      onToggleCard={() => setShown(shown === name ? null : name)}
                    />
                  );
                })}
              </ul>
            </PolicyControls.Provider>
          </>
        )}
      </Card>
    </div>
  );
}
