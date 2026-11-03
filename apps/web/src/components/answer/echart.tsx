"use client";

/**
 * One ECharts drawing, sized to its container and redrawn when the palette or
 * light/dark changes.
 *
 * Drawn as SVG: crisp at any zoom, selectable text, and it renders where there
 * is no canvas. Exporting a PNG uses a short-lived canvas instance instead,
 * because an SVG chart cannot rasterise itself.
 */

import { useEffect, useRef, useState } from "react";

import { useAppearanceVersion } from "@/lib/theme";
import { cn } from "@/lib/utils";

export type MakeOption = (width: number) => Record<string, unknown> | null;

/** The width below which charts use their compact layout. */
const NARROW = 520;

export function EChart({
  makeOption,
  height,
  className,
  testId,
}: {
  /** Builds the option from the page's current colours. Keep it stable. */
  makeOption: MakeOption;
  height: number;
  className?: string | undefined;
  testId?: string | undefined;
}) {
  const host = useRef<HTMLDivElement | null>(null);
  const appearance = useAppearanceVersion();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let disposed = false;
    let observer: ResizeObserver | null = null;
    let chart: { resize: () => void; dispose: () => void } | null = null;

    void (async () => {
      try {
        const { echarts } = await import("@/lib/echarts");
        if (disposed) return;
        let width = element.clientWidth;
        const option = makeOption(width);
        if (!option) {
          setFailed(true);
          return;
        }
        const instance = echarts.init(element, null, { renderer: "svg" });
        instance.setOption(option);
        chart = instance;
        if (typeof ResizeObserver !== "undefined") {
          observer = new ResizeObserver(() => {
            const next = element.clientWidth;
            // Crossing into or out of the compact layout redraws; otherwise
            // the same drawing is simply resized.
            if ((next < NARROW) !== (width < NARROW)) {
              const redrawn = makeOption(next);
              if (redrawn) instance.setOption(redrawn, { notMerge: true });
            }
            width = next;
            instance.resize();
          });
          observer.observe(element);
        }
      } catch {
        // The server already validated the spec, so this is a renderer
        // problem; the numbers are still under the answer's evidence.
        if (!disposed) setFailed(true);
      }
    })();

    return () => {
      disposed = true;
      observer?.disconnect();
      chart?.dispose();
    };
  }, [makeOption, appearance]);

  if (failed) {
    return (
      <p className="py-6 text-center text-[13.5px] text-muted-foreground">
        The chart could not be drawn in this browser. The numbers are in the evidence below.
      </p>
    );
  }

  return (
    <div
      ref={host}
      data-testid={testId}
      className={cn("w-full", className)}
      style={{ height: `${height}px` }}
    />
  );
}

/** A PNG of the option, drawn off-screen at twice the size for sharpness. */
export async function exportPng(
  option: Record<string, unknown>,
  width: number,
  height: number,
  background: string,
): Promise<string | null> {
  const { echarts } = await import("@/lib/echarts");
  const holder = document.createElement("div");
  holder.style.cssText = `position:fixed;left:-10000px;top:0;width:${width}px;height:${height}px;`;
  document.body.appendChild(holder);
  try {
    const instance = echarts.init(holder, null, { renderer: "canvas", width, height });
    instance.setOption({ ...option, animation: false });
    const url = instance.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: background });
    instance.dispose();
    return url;
  } catch {
    return null;
  } finally {
    holder.remove();
  }
}
