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
