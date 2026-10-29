import { describe, expect, test } from "vitest";
import {
  formatBytes,
  formatChange,
  formatCount,
  formatDate,
  formatMoney,
  formatPercent,
  formatPeriod,
  formatRatio,
  formatShortCount,
} from "./format";
import examplesFile from "./format-examples.json";

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
type Example = {
  kind: string;
  value?: string;
  currency?: string;
  style?: "short" | "full";
  unit?: string;
  start?: string;
  end?: string;
  expect: string;
};

const examples = (examplesFile as { examples: Example[] }).examples;

function formatExample(example: Example): string {
  switch (example.kind) {
    case "money":
      return formatMoney(example.value ?? "", example.currency ?? "USD", example.style ?? "short");
    case "count":
      return formatCount(example.value ?? "", example.style ?? "short");
    case "percent":
      return formatPercent(example.value ?? "");
    case "change":
      return formatChange(example.value ?? "", example.unit ?? "", example.currency ?? "USD", example.style ?? "short");
    case "ratio":
      return formatRatio(example.value ?? "");
    case "date":
      return formatDate(example.value ?? "");
    case "period":
      return formatPeriod(example.start ?? "", example.end ?? "");
    default:
      throw new Error(`unknown kind ${example.kind}`);
  }
}

describe("shared examples", () => {
  test.each(examples.map((example) => [example.expect, example] as [string, Example]))(
    "matches %s",
    (_expect, example) => {
      expect(formatExample(example)).toBe(example.expect);
    },
  );

  test("accepts numbers and strings", () => {
    expect(formatMoney(1415000)).toBe("$1.42M");
    expect(formatMoney("1415000")).toBe("$1.42M");
    expect(formatCount(400000, "full")).toBe("400,000");
    expect(formatPercent("6.2")).toBe("6.2%");
    expect(formatRatio(0.5)).toBe("0.50");
    expect(formatChange(-21400, "money")).toBe("−$21.4K");
  });
});
