/** A picture of an answer's own table, when the table is one a chart can show honestly. */

import { isDeltaColumn, looksNumeric, numberIn } from "./cells";

export interface DerivedChart {
  spec: Record<string, unknown>;
  /** Which column was plotted against which, for the figure's caption. */
  label: string;
  value: string;
}

const MONTHS: Record<string, number> = {
  jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, sept: 8, oct: 9, nov: 10, dec: 11,
};

/** "March 2025", "Mar 2025", "2025-03", "2025-03-14" → an ISO date; anything else → null. */
export function periodOf(text: string): { iso: string; unit: "yearmonth" | "yearmonthdate" } | null {
  const value = text.trim();
  const named = /^([A-Za-z]{3,9})\.?\s+(\d{4})$/.exec(value);
  if (named) {
    const month = MONTHS[named[1]!.slice(0, 4).toLowerCase()] ?? MONTHS[named[1]!.slice(0, 3).toLowerCase()];
    if (month === undefined) return null;
    return { iso: `${named[2]}-${String(month + 1).padStart(2, "0")}-01`, unit: "yearmonth" };
  }
  const yearMonth = /^(\d{4})-(\d{2})$/.exec(value);
  if (yearMonth) return { iso: `${yearMonth[1]}-${yearMonth[2]}-01`, unit: "yearmonth" };
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (day) return { iso: value, unit: "yearmonthdate" };
  return null;
}

/** The unit a column is written in, so the chart says "RM 28,204" and "−5.3%" too. */
function unitsOf(cells: string[]): { prefix: string; suffix: string } {
  const first = cells.find((cell) => cell.trim().length > 0)?.trim() ?? "";
  const currency = /^[+\-−(]?\s*(RM|MYR|USD|\$|€|£|¥|₹)\s?/i.exec(first)?.[1] ?? "";
  const suffix = cells.every((cell) => /%\s*\)?$/.test(cell.trim())) ? "%" : "";
  return { prefix: currency.length > 1 ? `${currency} ` : currency, suffix };
}

/** Repeated measure labels identify comparable columns. */
function measureOf(header: string): string | null {
  return /\b(net sales|gross sales|total sales|sales|revenue|order count|orders|average order value|average order|profit|units|quantity)\s*$/i
    .exec(header.trim())?.[1]?.toLowerCase() ?? null;
}

/** The chart a table supports, or null when it supports none. */
export function deriveChart(columns: string[], rows: string[][]): DerivedChart | null {
  if (rows.length < 3 || rows.length > 40 || columns.length < 2) return null;

  const cellsOf = (index: number) => rows.map((row) => row[index] ?? "");
  const numeric = columns.map((_, index) => {
    const cells = cellsOf(index).filter((cell) => cell.trim().length > 0);
    return cells.length === rows.length && cells.every(looksNumeric);
  });

  // The thing each row is about: a period if there is one, else the first column of words.
  const periodIndex = columns.findIndex((_, index) =>
    !numeric[index] && cellsOf(index).every((cell) => periodOf(cell) !== null),
  );
  const labelIndex =
    periodIndex >= 0 ? periodIndex : columns.findIndex((_, index) => !numeric[index]);
  if (labelIndex < 0) return null;

  const labels = cellsOf(labelIndex);
  if (new Set(labels).size !== labels.length) return null;

  // What to plot: a change column if there is one (the design's diverging bars).
  const candidates = columns
    .map((header, index) => ({ header, index }))
    .filter(({ index }) => index !== labelIndex && numeric[index])
    .filter(({ header }) => !/^(#|rank|no\.?|position)$/i.test(header.trim()));
  if (candidates.length === 0) return null;
  const delta = candidates.find(({ header, index }) => isDeltaColumn(header, cellsOf(index)));
  const chosen = delta ?? candidates[candidates.length - 1]!;

  const values = cellsOf(chosen.index).map(numberIn);
  if (values.some((value) => value === null)) return null;

  const labelHeader = columns[labelIndex] || "Item";
  const valueHeader = chosen.header || "Value";
  const field = { x: "label", y: "value" };
  const usermeta = unitsOf(cellsOf(chosen.index));

  if (periodIndex >= 0) {
    const periods = labels.map((label) => periodOf(label)!);
    const measure = measureOf(valueHeader);
    const comparable = candidates.filter(({ header, index }) => {
      const units = unitsOf(cellsOf(index));
      return !isDeltaColumn(header, cellsOf(index)) &&
        units.prefix === usermeta.prefix && units.suffix === usermeta.suffix &&
        measure !== null && measureOf(header) === measure;
    });
    const split = !delta && comparable.length > 1 && new Set(comparable.map(({ header }) => header)).size === comparable.length;
    const title = split ? (measure ?? "Value") : valueHeader;
    return {
      label: labelHeader,
      value: title,
      spec: {
        mark: "line",
        usermeta,
        title: `${title.charAt(0).toUpperCase()}${title.slice(1)} by ${labelHeader.toLowerCase()}`,
        encoding: {
          x: { field: field.x, type: "temporal", title: labelHeader, timeUnit: periods[0]!.unit },
          y: { field: field.y, type: "quantitative", title },
          ...(split ? { color: { field: "series", type: "nominal", title: "Series" } } : {}),
        },
        data: { values: split
          ? comparable.flatMap(({ header, index }) => periods.map((period, row) => ({
            label: period.iso, value: numberIn(rows[row]![index]!), series: header,
          })))
          : periods.map((period, index) => ({ label: period.iso, value: values[index] })) },
      },
    };
  }

  return {
    label: labelHeader,
    value: valueHeader,
    spec: {
      mark: "bar",
      usermeta,
      title: `${valueHeader} by ${labelHeader.toLowerCase()}`,
      encoding: {
        x: { field: field.x, type: "nominal", title: labelHeader },
        y: { field: field.y, type: "quantitative", title: valueHeader },
      },
      data: { values: labels.map((label, index) => ({ label, value: values[index] })) },
    },
  };
}
