import type { EChartsCoreOption } from "echarts/core";
import { echarts } from "./echarts";

/** File-safe name for a chart title, e.g. "Sales change" -> "sales-change.png". */
export function chartFileName(title: string): string {
  let slug = "";
  let dashed = true;
  for (const ch of title.toLowerCase()) {
    if ((ch >= "a" && ch <= "z") || (ch >= "0" && ch <= "9")) {
      slug += ch;
      dashed = false;
    } else if (!dashed) {
      slug += "-";
      dashed = true;
    }
  }
  if (slug.endsWith("-")) slug = slug.slice(0, -1);
  return `${slug || "chart"}.png`;
}

/**
 * Render an option off-screen with the canvas renderer and return a PNG data URL.
 * The on-screen chart stays on SVG; this copy exists only for the download.
 */
export function chartPngDataUrl(
  option: EChartsCoreOption,
  width = 1008,
  height = 420,
): string {
  const host = document.createElement("div");
  host.style.cssText = `position:absolute;left:-10000px;top:0;width:${width}px;height:${height}px;`;
  document.body.appendChild(host);
  try {
    const copy = echarts.init(host, null, { renderer: "canvas", ssr: false });
    copy.setOption({ ...option, animation: false });
    const url = copy.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
    copy.dispose();
    return url;
  } finally {
    host.remove();
  }
}

/** Render the option off-screen and trigger a PNG download. */
export function downloadChartPng(
  option: EChartsCoreOption,
  title: string,
  width?: number,
  height?: number,
): void {
  const url = chartPngDataUrl(option, width, height);
  const a = document.createElement("a");
  a.href = url;
  a.download = chartFileName(title);
  document.body.appendChild(a);
  a.click();
  a.remove();
}
