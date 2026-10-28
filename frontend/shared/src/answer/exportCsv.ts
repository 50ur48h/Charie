// CSV download for answer tables (P03.6). Numbers export as raw values
// (the machine-readable side of { v, f }); display strings stay on screen.
// The file starts with a UTF-8 BOM so Excel opens the −/·/… characters
// correctly, and uses CRLF line endings.
import type { Cell, TableBlock } from "../api/chat-types";

function escapeCell(text: string): string {
  if (
    text.includes('"') ||
    text.includes(",") ||
    text.includes("\n") ||
    text.includes("\r")
  ) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function guardFormula(text: string): string {
  // A text cell starting with = + - @ (or tab/CR) would run as a formula
  // in a spreadsheet. Prefixing one quote neutralizes it while leaving
  // numeric cells — including negatives — untouched.
  if (/^[=+\-@\t\r]/.test(text)) return `'${text}`;
  return text;
}

export function tableCsv(block: TableBlock): string {
  const header = block.columns.map((column) => escapeCell(column.label)).join(",");
  const lines = block.rows.map((row) =>
    block.columns
      .map((column) => {
        const cell: Cell = row[column.key];
        if (cell === null || cell === undefined) return "";
        if (typeof cell === "number") return String(cell);
        if (typeof cell === "object") return String(cell.v);
        return escapeCell(guardFormula(cell));
      })
      .join(","),
  );
  return `\uFEFF${[header, ...lines].join("\r\n")}\r\n`;
}

/** File-safe name for a table title, e.g. "Top 5" -> "top-5.csv". */
export function tableFileName(title: string): string {
  let slug = "";
  let dashed = true;
  for (const ch of title.toLowerCase()) {
    if ((ch >= "a" && ch <= "z") || (ch >= "0" && ch <= "9")) {
      slug += ch;
      dashed = false;
    } else if (!dashed) {
      slug += "-";
      dashed = true;
    }
  }
  if (slug.endsWith("-")) slug = slug.slice(0, -1);
  return `${slug || "table"}.csv`;
}
