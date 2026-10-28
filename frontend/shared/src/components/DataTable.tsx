import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { cn } from "./cn";

export function DataTable<T>({
  columns,
  data,
  empty = "Nothing here yet.",
  caption,
}: {
  columns: ColumnDef<T>[];
  data: T[];
  empty?: string;
  caption: string;
}) {
  const table = useReactTable({ columns, data, getCoreRowModel: getCoreRowModel() });
  const width = table.getAllLeafColumns().length;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm tabular-nums [ &_tr:last-child_td]:border-b-0">
        <caption className="sr-only">{caption}</caption>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th
                  key={header.id}
                  colSpan={header.colSpan}
                  className={cn(
                    "whitespace-nowrap border-b border-border px-3 py-2.5 text-left text-xs font-semibold text-muted",
                    numeric(header.column.columnDef) && "text-right",
                  )}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
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
