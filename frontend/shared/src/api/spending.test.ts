// The one-click raise target and the server validation messages (P12.2).
import { describe, expect, test } from "vitest";
import { nextLimit, validateLimit, validateWarn } from "./spending";

describe("nextLimit", () => {
  test("rounds the spend up, then up to the next 50", () => {
    expect(nextLimit(41.2)).toBe(50);
    expect(nextLimit(0)).toBe(50);
    expect(nextLimit(50)).toBe(100);
    expect(nextLimit(150)).toBe(200);
    expect(nextLimit(149.2)).toBe(200);
  });
});

describe("validateLimit", () => {
  test("keeps the server message", () => {
    expect(validateLimit("200")).toBeNull();
    expect(validateLimit("-5")).toBe("The monthly limit must be between $0.01 and $100,000.");
    expect(validateLimit("")).toBe("The monthly limit must be between $0.01 and $100,000.");
  });
});

describe("validateWarn", () => {
  test("keeps the server message", () => {
    expect(validateWarn("80")).toBeNull();
    expect(validateWarn("150")).toBe("The warning level must be a whole number from 1 to 99.");
  });
});
