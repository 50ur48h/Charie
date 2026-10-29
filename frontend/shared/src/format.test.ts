import { describe, expect, test } from "vitest";
import { formatBytes, formatShortCount } from "./format";

describe("formatShortCount", () => {
  test("shortens millions and thousands", () => {
    expect(formatShortCount(2_400_000)).toBe("2.4M");
    expect(formatShortCount(57)).toBe("57");
    expect(formatShortCount(1500)).toBe("1.5K");
    expect(formatShortCount(2_000_000)).toBe("2M");
    expect(formatShortCount(0)).toBe("0");
  });
});

describe("formatBytes", () => {
  test("sizes files the way the Sources rows do", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(18432)).toBe("18 KB");
    expect(formatBytes(1048576)).toBe("1 MB");
    expect(formatBytes(1258291)).toBe("1.2 MB");
  });
});
