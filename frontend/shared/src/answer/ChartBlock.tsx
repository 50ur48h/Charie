import { useCallback, useMemo, useRef, useState } from "react";
import { Download, Expand } from "lucide-react";
import { Button } from "../components/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "../components/Dialog";
import { Chart, type ChartHandle } from "../charts/Chart";
import { buildChartOption, chartSummary } from "../charts/chartBlockOption";
import { chartTheme, type ChartTheme } from "../theme/chartTheme";
import type { ChartBlock as ChartBlockType } from "../api/chat-types";

// One chart answer block: figure card with title, chart, screen-reader
// data summary, expand-to-dialog and PNG download. The dialog holds its
// own chart instance, so downloading there never shrinks the page chart.
export function ChartBlock({ block }: { block: ChartBlockType }) {
  const [open, setOpen] = useState(false);
  const chartRef = useRef<ChartHandle>(null);
  const dialogRef = useRef<ChartHandle>(null);
  const figure = useMemo(() => buildChartOption(block, chartTheme()), [block]);
  const build = useCallback(
    (theme: ChartTheme) => buildChartOption(block, theme)?.option ?? {},
    [block],
  );
  const label = block.subtitle ? `${block.title}. ${block.subtitle}` : block.title;

  if (!figure) {
    console.error(`Unsupported chart kind: ${block.kind}`);
    return <p className="text-[14px] text-muted">Chart unavailable.</p>;
  }
  return (
    <div className="mb-4 min-w-0 rounded-card border border-border bg-surface px-[18px] pb-3 pt-4 shadow-card">
      <div className="mb-2">
        <div className="font-serif text-[17px]">{block.title}</div>
        {block.subtitle !== undefined && block.subtitle !== "" && (
          <div className="mt-0.5 text-[12.5px] text-muted">{block.subtitle}</div>
        )}
      </div>
      <Chart ref={chartRef} label={label} height={figure.height} build={build} />
      <p className="sr-only">
        Data for {block.title}: {chartSummary(block)}.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => setOpen(true)} aria-label={`Expand: ${block.title}`}>
          <Expand aria-hidden="true" />
          Expand
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => chartRef.current?.downloadPng(block.title)}
          aria-label={`Download as image: ${block.title}`}
        >
          <Download aria-hidden="true" />
          Download as image
        </Button>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-[min(1040px,94vw)]">
          <DialogTitle>{block.title}</DialogTitle>
          {block.subtitle !== undefined && block.subtitle !== "" && (
            <DialogDescription>{block.subtitle}</DialogDescription>
          )}
          <div className="mt-3">
            <Chart ref={dialogRef} label={label} height={420} build={build} />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => dialogRef.current?.downloadPng(block.title)}
              aria-label={`Download as image: ${block.title}`}
            >
              <Download aria-hidden="true" />
              Download as image
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
