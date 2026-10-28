import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { Chart, type ChartHandle } from "./Chart";
import { chartTheme } from "../theme/chartTheme";

afterEach(cleanup);

const state = vi.hoisted(() => ({
  setOption: vi.fn(),
  dispose: vi.fn(),
  resize: vi.fn(),
  init: vi.fn(),
}));

const exportState = vi.hoisted(() => ({
  downloadChartPng: vi.fn(),
}));

vi.mock("./echarts", () => ({
  echarts: { init: state.init },
}));

vi.mock("./exportImage", () => ({
  downloadChartPng: exportState.downloadChartPng,
}));

state.init.mockReturnValue({
  setOption: state.setOption,
  dispose: state.dispose,
  resize: state.resize,
});

const build = vi.fn((theme: ReturnType<typeof chartTheme>) => ({
  series: [{ type: "bar" as const, data: [theme.barWidth] }],
}));

beforeEach(() => {
  state.init.mockClear();
  state.setOption.mockClear();
  state.dispose.mockClear();
  state.resize.mockClear();
  exportState.downloadChartPng.mockClear();
  build.mockClear();
});

describe("Chart", () => {
  test("has role img and the label", () => {
    render(<Chart build={build} height={200} label="Sales change by restaurant" />);
    expect(screen.getByRole("img", { name: "Sales change by restaurant" })).toBeTruthy();
  });

  test("draws after the fonts are ready", async () => {
    render(<Chart build={build} height={200} label="Sales change by restaurant" />);
    await waitFor(() => expect(state.init).toHaveBeenCalledTimes(1), { timeout: 3000 });
    expect(state.setOption).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("img").dataset.chartReady).toBe("true");
  });

  test("redraws when the theme changes", async () => {
    render(<Chart build={build} height={200} label="Sales change by restaurant" />);
    await waitFor(() => expect(state.setOption).toHaveBeenCalledTimes(1));
    window.dispatchEvent(new CustomEvent("themechange", { detail: "mauve" }));
    await waitFor(() => expect(state.setOption).toHaveBeenCalledTimes(2));
    expect(state.setOption.mock.calls[1][1]).toEqual({ notMerge: true });
  });

  test("downloadPng saves a PNG named after the title", async () => {
    const ref: { current: ChartHandle | null } = { current: null };
    render(<Chart ref={ref} build={build} height={200} label="Sales change by restaurant" />);
    await waitFor(() => expect(state.init).toHaveBeenCalledTimes(1), { timeout: 3000 });
    ref.current?.downloadPng("Sales change by restaurant");
    expect(exportState.downloadChartPng).toHaveBeenCalledWith(
      expect.anything(),
      "Sales change by restaurant",
      expect.any(Number),
      expect.any(Number),
    );
  });

  test("disposes the chart when removed", async () => {
    const { unmount } = render(
      <Chart build={build} height={200} label="Sales change by restaurant" />,
    );
    await waitFor(() => expect(state.init).toHaveBeenCalledTimes(1));
    unmount();
    expect(state.dispose).toHaveBeenCalledTimes(1);
    window.dispatchEvent(new CustomEvent("themechange", { detail: "sage" }));
    await new Promise((r) => setTimeout(r, 50));
    expect(state.setOption).toHaveBeenCalledTimes(1);
  });
});
