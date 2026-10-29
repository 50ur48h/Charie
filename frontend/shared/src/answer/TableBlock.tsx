import { useMemo } from "react";
import type {
  CellContext,
  ColumnDef,
  Row as TableRow,
} from "@tanstack/react-table";
import { Download } from "lucide-react";
import { Button } from "../components/Button";
import { DataTable } from "../components/DataTable";
import type { Cell, TableBlock as TableBlockType } from "../api/chat-types";
import { tableCsv, tableFileName } from "./exportCsv";

type Row = Record<string, Cell>;
type Raw = string | number | null;

function display(cell: Cell): string {
  if (cell === null || cell === undefined) return "";
  if (typeof cell === "object") return cell.f;
  return String(cell);
}

function raw(cell: Cell): Raw {
  if (cell === null || cell === undefined) return null;
  if (typeof cell === "object") return cell.v;
  return cell;
}

function compareRaw(
  a: TableRow<Row>,
  b: TableRow<Row>,
  id: string,
): number {
  const av = a.getValue(id) as Raw;
  const bv = b.getValue(id) as Raw;
  if (av === null || av === undefined) return 1;
  if (bv === null || bv === undefined) return -1;
  if (typeof av === "number" && typeof bv === "number") return av - bv;
  return display(av).localeCompare(display(bv));
}

function downloadCsv(title: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = tableFileName(title);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// One table answer block: sortable columns (raw values sort, formatted
// values show) and a CSV download of the block's own rows. A column
// counts as numeric — and right-aligns — only when every value in it is.
export function TableBlock({ block }: { block: TableBlockType }) {
  const columns = useMemo<ColumnDef<Row, Raw>[]>(
    () =>
      block.columns.map((column) => {
        const numeric = block.rows.every((row) => {
          const value = raw(row[column.key]);
          return value === null || typeof value === "number";
        });
        return {
          id: column.key,
          header: column.label,
          accessorFn: (row: Row) => raw(row[column.key]),
          cell: (info: CellContext<Row, Raw>) =>
            display(info.row.original[column.key]),
          sortingFn: compareRaw,
          // First click sorts small-to-large: explicit, not library default.
          sortDescFirst: false,
          meta: numeric ? { numeric: true } : {},
        };
      }),
    [block],
  );
  const data = useMemo(
    () =>
      block.rows.map((row) => {
        const out: Row = {};
        for (const column of block.columns) out[column.key] = row[column.key] ?? null;
        return out;
      }),
    [block],
  );
  return (
    <div className="mb-4 min-w-0 rounded-card border border-border bg-surface px-[18px] pb-3 pt-4 shadow-card">
      <div className="mb-2 font-serif text-[17px]">{block.title}</div>
      <DataTable
        columns={columns}
        data={data}
        caption={block.title}
        sortable
        empty="No rows."
      />
      <div className="block-tools mt-2 print:hidden">
        <Button
          variant="outline"
          size="sm"
          onClick={() => downloadCsv(block.title, tableCsv(block))}
          aria-label={`Download as CSV: ${block.title}`}
        >
          <Download aria-hidden="true" />
          Download as CSV
        </Button>
      </div>
    </div>
  );
}
