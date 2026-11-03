"use client";

/**
 * The chart, or the reason there is none (WP11.1, B-048).
 *
 * **Inside the answer**, because a chart beside the answer is a picture next to
 * some prose, while a chart inside it is part of the claim. And **its spec opens
 * the way the SQL does**: a picture nobody can check is decoration that looks
 * like evidence.
 *
 * **A refusal renders here too, in the chart's own place.** It is deliberately
 * not a limitation — that list is about whether the answer is true, and a
 * missing picture says nothing about that.
 */

import { Braces, ChartNoAxesColumn, Download, Maximize2 } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { RunChart } from "@/lib/api-client";

import { buildChart, readChartTheme, type ChartTheme } from "./chart-option";
import { EChart, exportPng } from "./echart";
import { Figure, FigureAction } from "./figure";

/** Titles, subtitles and heights do not depend on colour; this stands in on the server. */
const NEUTRAL: ChartTheme = {
  font: "Inter",
  text: "#232a22",
  muted: "#7a8477",
  grid: "#e2e7dd",
  accent: "#6e9277",
  pos: "#b5cdb9",
  neg: "#ebc2bb",
  bad: "#c2554a",
  good: "#4e8a5e",
  surface: "#ffffff",
  border: "#dfe5da",
  categories: ["#6e9277", "#c9a15a", "#7fa7c9", "#c98b8b", "#9c8cc4", "#6fafa5", "#b0a46e", "#9a9a9a"],
};

export function AnswerChart({ chart }: { chart: RunChart | null | undefined }) {
  const spec = chart?.spec ?? null;
  const [showSpec, setShowSpec] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const area = useRef<HTMLDivElement | null>(null);

  const built = useMemo(() => (spec ? buildChart(spec, NEUTRAL) : null), [spec]);
  const makeOption = useCallback(
    (width: number) => (spec ? (buildChart(spec, readChartTheme(), { width })?.option ?? null) : null),
    [spec],
  );

  const download = useCallback(async () => {
    if (!spec || !built) return;
    const theme = readChartTheme();
    const option = buildChart(spec, theme)?.option;
    const width = Math.max(640, area.current?.clientWidth ?? 760);
    const url = option ? await exportPng(option, width, built.height, theme.surface) : null;
    if (!url) {
      toast("The image could not be made in this browser.");
      return;
    }
    const link = document.createElement("a");
    link.href = url;
    link.download = `${built.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "chart"}.png`;
    link.click();
  }, [spec, built]);

  if (!chart) return null;

  if (!spec) {
    return (
      <div className="flex items-start gap-2.5 rounded-md border border-dashed border-faint px-3.5 py-2.5 font-sans text-[13.5px] leading-relaxed text-muted-foreground">
        <ChartNoAxesColumn aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-brand" />
        <p>{chart.declined ?? "No chart was drawn."}</p>
      </div>
    );
  }

  const specToggle = (
    <FigureAction
      label={showSpec ? "Hide chart spec" : "Chart spec"}
      pressed={showSpec}
      onClick={() => setShowSpec((open) => !open)}
    >
      <Braces />
    </FigureAction>
  );

  return (
    <Figure
      title={built?.title ?? "Chart"}
      subtitle={built?.subtitle}
      actions={
        <>
          {built && (
            <FigureAction label="Download as image" onClick={() => void download()}>
              <Download />
            </FigureAction>
          )}
          {built && (
            <FigureAction label="Full screen" onClick={() => setExpanded(true)}>
              <Maximize2 />
            </FigureAction>
          )}
          {specToggle}
        </>
      }
    >
      <div ref={area}>
        {built ? (
          <EChart testId="chart" makeOption={makeOption} height={built.height} />
        ) : (
          <p data-testid="chart" className="py-6 text-center text-[13.5px] text-muted-foreground">
            This chart uses a shape this screen does not draw. The spec is below, and the numbers
            are in the evidence.
          </p>
        )}
      </div>
      {showSpec && (
        <pre className="mt-3 max-h-72 overflow-auto rounded-md bg-code px-3.5 py-3 font-mono text-[12px] leading-relaxed text-code-ink">
          {JSON.stringify(spec, null, 2)}
        </pre>
      )}
      {built && (
        <Dialog open={expanded} onOpenChange={setExpanded}>
          <DialogContent className="w-[min(1100px,94vw)] max-w-none sm:max-w-none">
            <DialogTitle className="font-serif text-[19px]">{built.title}</DialogTitle>
            {built.subtitle && <DialogDescription>{built.subtitle}</DialogDescription>}
            {expanded && <EChart makeOption={makeOption} height={Math.max(440, Math.round(built.height * 1.45))} />}
          </DialogContent>
        </Dialog>
      )}
    </Figure>
  );
}
