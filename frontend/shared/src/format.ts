// Short counts for facts and stats ("2.4M rows", P04.2+). One decimal, with
// the ".0" trimmed; millions, thousands, then plain.
// File sizes for the Sources rows ("1.2 MB"): B, KB, MB, GB, one decimal
// with the ".0" trimmed.
export function formatBytes(n: number): string {
  if (n >= 1024 ** 3) return trimSize(n / 1024 ** 3, " GB");
  if (n >= 1024 ** 2) return trimSize(n / 1024 ** 2, " MB");
  if (n >= 1024) return trimSize(n / 1024, " KB");
  return `${n} B`;
}

function trimSize(value: number, suffix: string): string {
  const rounded = Math.round(value * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded.toFixed(0) : String(rounded)}${suffix}`;
}

export function formatShortCount(n: number): string {
  const trim = (value: number, suffix: string): string => {
    const rounded = Math.round(value * 10) / 10;
    return `${Number.isInteger(rounded) ? rounded.toFixed(0) : String(rounded)}${suffix}`;
  };
  if (n >= 1_000_000) return trim(n / 1_000_000, "M");
  if (n >= 1_000) return trim(n / 1_000, "K");
  return String(n);
}

// Shared number rules (P05.6): the same examples file tests these and
// backend/charie/shared/text/numbers.py, so the two can never disagree.
// Rounding works on the decimal string (never toFixed on a float), half away
// from zero; the minus sign is U+2212, the period dash U+2013.
const FORMAT_MINUS = "−";
const FORMAT_EN_DASH = "–";

const FORMAT_CURRENCIES: Record<string, string> = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  INR: "₹",
};

const FORMAT_MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const FORMAT_UNITS: Array<[string, number]> = [
  ["B", 9],
  ["M", 6],
  ["K", 3],
];

export type MoneyStyle = "short" | "full";

function formatParts(value: number | string): { neg: boolean; abs: string } {
  const raw = typeof value === "number" ? String(value) : value.trim();
  const unsigned = raw.startsWith("-") ? raw.slice(1) : raw.startsWith("+") ? raw.slice(1) : raw;
  if (!/^\d+(\.\d+)?([eE][+-]?\d+)?$/.test(unsigned)) throw new Error(`${raw} is not a number.`);
  return { neg: raw.startsWith("-"), abs: expandExponent(unsigned) };
}

function expandExponent(abs: string): string {
  if (!/[eE]/.test(abs)) return abs;
  const [mantissa, expText] = abs.toLowerCase().split("e");
  const exp = Number(expText);
  const digits = mantissa.replace(".", "");
  const dot = mantissa.includes(".") ? mantissa.indexOf(".") : mantissa.length;
  return shiftPointDigits(digits, dot + exp);
}

function shiftPointDigits(digits: string, point: number): string {
  const clean = digits.replace(/^0+(?=\d)/, "") || "0";
  if (point <= 0) return `0.${"0".repeat(-point)}${clean}`;
  if (point >= clean.length) return clean + "0".repeat(point - clean.length);
  return `${clean.slice(0, point)}.${clean.slice(point)}`;
}

function shiftPoint(abs: string, exp: number): string {
  const dot = abs.indexOf(".");
  const int = dot === -1 ? abs : abs.slice(0, dot);
  const frac = dot === -1 ? "" : abs.slice(dot + 1);
  return shiftPointDigits(int + frac, int.length - exp);
}

function addOne(digits: string): string {
  const arr = digits.split("");
  for (let i = arr.length - 1; i >= 0; i--) {
    if (arr[i] === "9") {
      arr[i] = "0";
    } else {
      arr[i] = String(Number(arr[i]) + 1);
      return arr.join("");
    }
  }
  return `1${arr.join("")}`;
}

function roundHalfUp(abs: string, places: number): string {
  const dot = abs.indexOf(".");
  const int = (dot === -1 ? abs : abs.slice(0, dot)).replace(/^0+/, "") || "0";
  const frac = dot === -1 ? "" : abs.slice(dot + 1);
  const padded = (frac + "0".repeat(places)).slice(0, places);
  const keep = int + padded;
  const next = frac.length > places ? Number(frac[places]) : 0;
  const digits = next >= 5 ? addOne(keep) : keep;
  if (places === 0) return digits;
  return `${digits.slice(0, digits.length - places)}.${digits.slice(digits.length - places)}`;
}

function dropZeros(text: string): string {
  if (!text.includes(".")) return text;
  return text.replace(/0+$/, "").replace(/\.$/, "");
}

function integerDigits(abs: string): number {
  const dot = abs.indexOf(".");
  const int = (dot === -1 ? abs : abs.slice(0, dot)).replace(/^0+/, "") || "0";
  return int === "0" ? 1 : int.length;
}

function isZeroAbs(abs: string): boolean {
  return /^0*(\.0*)?$/.test(abs);
}

function isTinyAbs(abs: string): boolean {
  if (isZeroAbs(abs)) return false;
  const dot = abs.indexOf(".");
  if (dot === -1) return false;
  if (abs.slice(0, dot).replace(/^0+/, "") !== "") return false;
  const leading = abs.slice(dot + 1).match(/^0*/)?.[0].length ?? 0;
  return leading >= 2;
}

function groupThousands(whole: string): string {
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function shortScaled(abs: string): [string, string] {
  for (let i = 0; i < FORMAT_UNITS.length; i++) {
    const [suffix, exp] = FORMAT_UNITS[i];
    if (integerDigits(abs) > exp) {
      const scaled = shiftPoint(abs, exp);
      const digits = integerDigits(scaled);
      const rounded = roundHalfUp(scaled, digits >= 3 ? 0 : digits === 2 ? 1 : 2);
      if (integerDigits(rounded) > 3 && i > 0) {
        const [bigger, biggerExp] = FORMAT_UNITS[i - 1];
        const up = shiftPoint(abs, biggerExp);
        const upDigits = integerDigits(up);
        const upRounded = roundHalfUp(up, upDigits >= 3 ? 0 : upDigits === 2 ? 1 : 2);
        return [dropZeros(upRounded), bigger];
      }
      return [dropZeros(rounded), suffix];
    }
  }
  return [dropZeros(roundHalfUp(abs, 2)), ""];
}

export function formatMoney(
  value: number | string,
  currency = "USD",
  style: MoneyStyle = "short",
): string {
  const { neg, abs } = formatParts(value);
  const symbol = FORMAT_CURRENCIES[currency] ?? (currency ? `${currency} ` : "");
  const sign = neg && !isZeroAbs(abs) ? FORMAT_MINUS : "";
  if (isTinyAbs(abs)) {
    return `${sign}<${symbol}0.01`;
  }
  if (integerDigits(abs) <= 3) return `${sign}${symbol}${roundHalfUp(abs, 2)}`;
  if (style === "full") return `${sign}${symbol}${groupThousands(roundHalfUp(abs, 0))}`;
  const [scaled, suffix] = shortScaled(abs);
  return `${sign}${symbol}${scaled}${suffix}`;
}

export function formatCount(value: number | string, style: MoneyStyle = "short"): string {
  const { neg, abs } = formatParts(value);
  const whole = roundHalfUp(abs, 0);
  const sign = neg && !isZeroAbs(abs) ? FORMAT_MINUS : "";
  if (style === "short" && integerDigits(whole) > 4) {
    const [scaled, suffix] = shortScaled(whole);
    return `${sign}${scaled}${suffix}`;
  }
  return `${sign}${groupThousands(whole)}`;
}

export function formatPercent(value: number | string): string {
  const { neg, abs } = formatParts(value);
  const sign = neg && !isZeroAbs(abs) ? FORMAT_MINUS : "";
  return `${sign}${dropZeros(roundHalfUp(abs, 1))}%`;
}

export function formatChange(
  value: number | string,
  unit: string,
  currency = "USD",
  style: MoneyStyle = "short",
): string {
  if (unit !== "money" && unit !== "count" && unit !== "percent") {
    throw new Error(`Unknown unit "${unit}". Use money, count or percent.`);
  }
  const { neg, abs } = formatParts(value);
  if (isZeroAbs(abs)) {
    if (unit === "money") return formatMoney(0, currency, style);
    return unit === "count" ? "0" : "0%";
  }
  const sign = neg ? FORMAT_MINUS : "+";
  if (unit === "money") return `${sign}${formatMoney(abs, currency, style)}`;
  if (unit === "count") return `${sign}${formatCount(abs, style)}`;
  return `${sign}${formatPercent(abs)}`;
}

export function formatRatio(value: number | string): string {
  const { neg, abs } = formatParts(value);
  const sign = neg && !isZeroAbs(abs) ? FORMAT_MINUS : "";
  return `${sign}${roundHalfUp(abs, 2)}`;
}

function parseDay(text: string): { day: number; month: number; year: number } {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text.trim());
  if (!match) throw new Error(`${text} is not a day like 2025-12-31.`);
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    throw new Error(`${text} is not a day like 2025-12-31.`);
  }
  return { day, month, year };
}

export function formatDate(day: string): string {
  const parsed = parseDay(day);
  return `${parsed.day} ${FORMAT_MONTHS[parsed.month - 1]} ${parsed.year}`;
}

export function formatPeriod(start: string, end: string): string {
  const first = parseDay(start);
  const last = parseDay(end);
  if (start.trim() === end.trim()) return formatDate(start);
  if (first.year === last.year && first.month === last.month) {
    return `${first.day}${FORMAT_EN_DASH}${last.day} ${FORMAT_MONTHS[last.month - 1]} ${last.year}`;
  }
  if (first.year === last.year) {
    return `${first.day} ${FORMAT_MONTHS[first.month - 1]} ${FORMAT_EN_DASH} ${last.day} ${FORMAT_MONTHS[last.month - 1]} ${last.year}`;
  }
  return `${formatDate(start)} ${FORMAT_EN_DASH} ${formatDate(end)}`;
}
