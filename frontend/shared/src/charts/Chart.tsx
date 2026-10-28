import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { echarts } from "./echarts";
import { downloadChartPng } from "./exportImage";
import { fontsReady } from "../theme/fonts";
import { chartTheme, type ChartTheme } from "../theme/chartTheme";
import { THEME_CHANGE_EVENT } from "../theme/theme";

export interface ChartProps {
  build: (theme: ChartTheme) => EChartsCoreOption;
  height: number;
  label: string;
  className?: string;
}

export interface ChartHandle {
  downloadPng: (title: string) => void;
}

export const Chart = forwardRef<ChartHandle, ChartProps>(function Chart(
  { build, height, label, className },
  ref,
) {
  const divRef = useRef<HTMLDivElement>(null);
  const buildRef = useRef(build);
  buildRef.current = build;

  useImperativeHandle(ref, () => ({
    downloadPng: (title: string) => {
      const el = divRef.current;
      if (!el) return;
      downloadChartPng(
        buildRef.current(chartTheme()),
        title,
        Math.max(320, Math.round(el.clientWidth || 1008)),
        Math.max(200, Math.round(el.clientHeight || height)),
      );
    },
  }));

  useEffect(() => {
    const el = divRef.current;
    if (!el) return;
    let chart: ReturnType<typeof echarts.init> | null = null;
    let observer: ResizeObserver | null = null;
    let cancelled = false;
    const reduceMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const draw = (): void => {
      if (!chart) return;
      const option = buildRef.current(chartTheme()) as EChartsCoreOption & {
        animation?: boolean;
      };
      if (reduceMotion) option.animation = false;
      chart.setOption(option, { notMerge: true });
    };
    const onThemeChange = (): void => draw();

    fontsReady().then(() => {
      if (cancelled) return;
      chart = echarts.init(el, null, { renderer: "svg" });
      draw();
      el.dataset.chartReady = "true";
      observer = new ResizeObserver(() => chart?.resize());
      observer.observe(el);
      window.addEventListener(THEME_CHANGE_EVENT, onThemeChange);
    });

    return () => {
      cancelled = true;
      window.removeEventListener(THEME_CHANGE_EVENT, onThemeChange);
      observer?.disconnect();
      chart?.dispose();
      chart = null;
    };
  }, [build]);

  return (
    <div
      ref={divRef}
      role="img"
      aria-label={label}
      className={className}
      style={{ width: "100%", height }}
    />
  );
});
