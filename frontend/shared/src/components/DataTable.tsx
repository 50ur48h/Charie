import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { cn } from "./cn";

export function DataTable<T>({
  columns,
  data,
  empty = "Nothing here yet.",
  caption,
  sortable = false,
}: {
  columns: ColumnDef<T>[];
  data: T[];
  empty?: string;
  caption: string;
  sortable?: boolean;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({
    columns,
    data,
    getCoreRowModel: getCoreRowModel(),
    ...(sortable
      ? {
          getSortedRowModel: getSortedRowModel(),
          onSortingChange: setSorting,
          state: { sorting },
        }
      : {}),
  });
  const width = table.getAllLeafColumns().length;
  return (
    <div className="overflow-x-auto" role="region" aria-label={caption} tabIndex={0}>
      <table className="w-full border-collapse text-sm tabular-nums [ &_tr:last-child_td]:border-b-0">
        <caption className="sr-only">{caption}</caption>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => {
                const sorted = header.column.getIsSorted();
                const num = numeric(header.column.columnDef);
                const label = flexRender(
                  header.column.columnDef.header,
                  header.getContext(),
                );
                return (
                  <th
                    key={header.id}
                    colSpan={header.colSpan}
                    aria-sort={
                      sortable && sorted
                        ? sorted === "asc"
                          ? "ascending"
                          : "descending"
                        : undefined
                    }
                    className={cn(
                      "whitespace-nowrap border-b border-border px-3 py-2.5 text-left text-xs font-semibold text-muted",
                      num && "text-right",
                    )}
                  >
                    {sortable ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        aria-label={
                          typeof header.column.columnDef.header === "string"
                            ? `Sort by ${header.column.columnDef.header}`
                            : `Sort by column ${header.id}`
                        }
                        className={cn(
                          "inline-flex cursor-pointer items-center gap-1 hover:text-text",
                          num && "float-right",
                        )}
                      >
                        {label}
                        {sorted === "asc" && <ArrowUp size={13} aria-hidden="true" />}
                        {sorted === "desc" && <ArrowDown size={13} aria-hidden="true" />}
                      </button>
                    ) : (
                      label
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.length === 0 ? (
            <tr>
              <td colSpan={width} className="px-3 py-3 align-middle text-muted">
                {empty}
              </td>
            </tr>
          ) : (
            table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="transition-[background-color] duration-150 hover:bg-[rgba(var(--shadow-rgb),.03)]"
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={cn(
                      "border-b border-border-soft px-3 py-3 align-middle",
                      numeric(cell.column.columnDef) && "text-right",
                    )}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function numeric<T>(def: ColumnDef<T, unknown>): boolean {
  return (def.meta as { numeric?: boolean } | undefined)?.numeric === true;
}
