import { cleanup } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { chartTheme } from "./chartTheme";

afterEach(cleanup);

describe("chartTheme", () => {
  test("reads the chart colors from the theme variables", () => {
    document.documentElement.style.setProperty("--text", "#232A22");
    document.documentElement.style.setProperty("--chart-muted", "#7A8477");
    document.documentElement.style.setProperty("--accent", "#6E9277");
    try {
      const theme = chartTheme();
      expect(theme.font).toBe("Inter");
      expect(theme.gridType).toBe("dashed");
      expect(theme.barRadius).toBe(6);
      expect(theme.barWidth).toBe(14);
      expect(theme.text).toBe("#232A22");
      expect(theme.muted).toBe("#7A8477");
      expect(theme.accent).toBe("#6E9277");
    } finally {
      document.documentElement.style.removeProperty("--text");
      document.documentElement.style.removeProperty("--chart-muted");
      document.documentElement.style.removeProperty("--accent");
    }
  });
});
