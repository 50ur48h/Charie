/** Reading a table cell the way a reader would: is it a number, which way does it point. */

const MINUS = /[−–]/g;

/** Whether a cell holds a number rather than words. */
export function looksNumeric(text: string): boolean {
  const value = text.trim().replace(MINUS, "-");
  if (value.length === 0) return false;
  return /^[-+(]?\s*(RM|MYR|USD|\$|€|£|¥|₹)?\s*[-+]?\s*[\d,]+(\.\d+)?\s*(%|[KMB]|x)?\s*\)?$/i.test(value);
}

/** The number a numeric-looking cell stands for, for sorting. */
export function numberIn(text: string): number | null {
  const value = text.trim().replace(MINUS, "-");
  if (!looksNumeric(value)) return null;
  const negative = /^\(.*\)$/.test(value) || /^-|^[^\d]*-\s*\d/.test(value);
  const digits = value.replace(/[^\d.]/g, "");
  if (digits.length === 0) return null;
  let parsed = Number(digits);
  if (!Number.isFinite(parsed)) return null;
  const suffix = /([KMB])\s*\)?$/i.exec(value)?.[1]?.toUpperCase();
  if (suffix === "K") parsed *= 1e3;
  if (suffix === "M") parsed *= 1e6;
  if (suffix === "B") parsed *= 1e9;
  return negative ? -parsed : parsed;
}

/** "+14.8%" points up, "−2.4%" points down; a bare number points nowhere. */
export function signedTone(text: string): "up" | "down" | null {
  const value = text.trim().replace(MINUS, "-");
  if (/^\+\s?[$€£]?\d/.test(value)) return "up";
  if (/^-\s?[$€£]?\d/.test(value)) return "down";
  return null;
}

/** A column of changes ("vs last month", "Change") reads as pills, like the design. */
export function isDeltaColumn(header: string, cells: string[]): boolean {
  const filled = cells.filter((cell) => cell.trim().length > 0);
  if (filled.length === 0) return false;
  const signed = filled.every((cell) => signedTone(cell) !== null || /^0(\.0+)?\s*%?$/.test(cell.trim()));
  if (!signed) return false;
  const percent = filled.every((cell) => /%\s*$/.test(cell.trim()));
  return percent || /(change|vs\.?|growth|delta|diff|difference|movement)/i.test(header);
}

const UP_WORDS =
  /\b(up|rose|risen|grew|grown|growing|increased?|increases|increasing|gain(?:ed|s)?|higher|jump(?:ed|s)?|climb(?:ed|s)?|surged?|boost(?:ed)?|improved?|improving|record high|ahead)\b/i;
const DOWN_WORDS =
  /\b(down|fell|fallen|falling|drop(?:ped|s)?|declined?|declines|declining|decreased?|decreases|decreasing|lower|lost|loss(?:es)?|shrank|shrunk|slump(?:ed)?|plunged?|dipped|behind|short(?:fall)?)\b/i;

/** Which way an emphasised phrase points, if it carries a number and a direction — "up 6.2%". */
export function markTone(text: string): "up" | "down" | null {
  if (!/\d/.test(text)) return null;
  const value = text.replace(MINUS, "-");
  const up = UP_WORDS.test(value) || /(^|[\s(])\+\s?[$€£]?\d/.test(value);
  const down = DOWN_WORDS.test(value) || /(^|[\s(])-\s?[$€£]?\d/.test(value);
  if (up === down) return null;
  return up ? "up" : "down";
}
