"use client";

/** A result table in the Calm style, on TanStack Table. */

import {
  createColumnHelper,
  createSortedRowModel,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useMemo, type ReactNode } from "react";

import { cn } from "@/lib/utils";

import { isDeltaColumn, looksNumeric, numberIn, signedTone } from "./cells";

export interface TableColumn {
  label: string;
  /** Something to show after the label, such as a "masked" badge. */
  badge?: ReactNode;
}

interface RowData {
  cells: string[];
}

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric, basic: sortFn_basic },
});

const helper = createColumnHelper<typeof features, RowData>();

/** Comma-separated values, quoted, with a typographic minus turned back into "-". */
export function toCsv(columns: string[], rows: string[][]): string {
  const quote = (value: string) => `"${value.replace(/−/g, "-").replace(/"/g, '""')}"`;
  return [columns, ...rows].map((row) => row.map(quote).join(",")).join("\n");
}

export function downloadCsv(name: string, columns: string[], rows: string[][]): void {
  const blob = new Blob([toCsv(columns, rows)], { type: "text/csv" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "table"}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

export function DataTable({
  columns,
  rows,
  highlight,
  maxHeight,
  className,
  caption,
}: {
  columns: TableColumn[];
  rows: string[][];
  /** A row to call out, by its first cell — as the design does for the outlier. */
  highlight?: string | undefined;
  /** Scroll inside the table past this height. */
  maxHeight?: number | undefined;
  className?: string | undefined;
  caption?: string | undefined;
}) {
  const kinds = useMemo(
    () =>
      columns.map((column, index) => {
        const cells = rows.map((row) => row[index] ?? "");
        const filled = cells.filter((cell) => cell.trim().length > 0);
        const numeric = filled.length > 0 && filled.every(looksNumeric);
        return { numeric, delta: numeric && isDeltaColumn(column.label, cells) };
      }),
    [columns, rows],
  );

  const tableColumns = useMemo(
    () =>
      helper.columns(
        columns.map((column, index) =>
          helper.accessor((row) => {
            const text = row.cells[index] ?? "";
            return kinds[index]?.numeric ? (numberIn(text) ?? Number.NEGATIVE_INFINITY) : text;
          }, {
            id: `c${index}`,
            header: column.label,
            sortFn: kinds[index]?.numeric ? "basic" : "alphanumeric",
            sortDescFirst: kinds[index]?.numeric ?? false,
          }),
        ),
      ),
    [columns, kinds],
  );

  const data = useMemo(() => rows.map((cells) => ({ cells })), [rows]);
  const table = useTable({ features, columns: tableColumns, data });

  return (
    <div
      className={cn("overflow-auto", className)}
      style={maxHeight ? { maxHeight: `${maxHeight}px` } : undefined}
    >
      <table className="w-full border-collapse font-sans text-[13.5px] tabular-nums">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header, index) => {
                const sorted = header.column.getIsSorted();
                const numeric = kinds[index]?.numeric ?? false;
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                    className={cn(
                      "sticky top-0 border-b border-border bg-surface px-2 py-2 align-bottom text-[12px] font-semibold whitespace-nowrap text-muted-foreground",
                      numeric ? "text-right" : "text-left",
                    )}
                  >
                    <button
                      type="button"
                      onClick={header.column.getToggleSortingHandler()}
                      className={cn(
                        "group/sort inline-flex items-center gap-1 rounded-[6px] transition-colors hover:text-text",
                        numeric && "flex-row-reverse",
                      )}
                    >
                      {columns[index]?.label}
                      {sorted === "asc" ? (
                        <ArrowUp aria-hidden="true" className="size-3" />
                      ) : sorted === "desc" ? (
                        <ArrowDown aria-hidden="true" className="size-3" />
                      ) : (
                        <ArrowUpDown aria-hidden="true" className="size-3 opacity-0 transition-opacity group-hover/sort:opacity-60" />
                      )}
                    </button>
                    {columns[index]?.badge}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, position) => {
            const called = highlight !== undefined && row.original.cells[0] === highlight;
            return (
              <tr
                key={row.id}
                className={cn(
                  "animate-fade-up transition-colors hover:bg-surface-2/60",
                  called && "bg-bad-soft hover:bg-bad-soft",
                )}
                style={{ animationDelay: `${Math.min(position, 12) * 60}ms` }}
              >
                {row.original.cells.map((text, index) => {
                  const kind = kinds[index];
                  const tone = kind?.delta ? signedTone(text) : null;
                  return (
                    <td
                      key={index}
                      className={cn(
                        "border-b border-border-soft px-2 py-2.5 align-top",
                        kind?.numeric ? "text-right whitespace-nowrap" : "text-left",
                        position === rows.length - 1 && "border-b-0",
                        called && index === 0 && "rounded-l-[8px] font-semibold",
                        called && index === row.original.cells.length - 1 && "rounded-r-[8px]",
                      )}
                    >
                      {tone ? (
                        <span
                          className={cn(
                            "inline-block rounded-full px-2 py-0.5 text-[12px] font-semibold",
                            tone === "up" ? "bg-good-soft text-good-ink" : "bg-bad-soft text-bad-ink",
                          )}
                        >
                          {text}
                        </span>
                      ) : (
                        text
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
