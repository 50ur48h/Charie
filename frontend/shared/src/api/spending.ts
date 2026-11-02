// Spending helpers (P12.2): the one-click raise target and the server's
// validation messages, shared by the limits dialog and the Usage page.
export function nextLimit(spentUsd: number): number {
  return Math.floor(Math.ceil(spentUsd) / 50) * 50 + 50;
}

export function validateLimit(value: string): string | null {
  const num = Number(value);
  if (value.trim() === "" || !Number.isFinite(num) || num < 0.01 || num > 100000) {
    return "The monthly limit must be between $0.01 and $100,000.";
  }
  return null;
}

export function validateWarn(value: string): string | null {
  const num = Number(value);
  if (value.trim() === "" || !Number.isInteger(num) || num < 1 || num > 99) {
    return "The warning level must be a whole number from 1 to 99.";
  }
  return null;
}
