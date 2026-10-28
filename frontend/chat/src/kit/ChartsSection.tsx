import { useCallback, useRef } from "react";
import {
  Button,
  Chart,
  barOption,
  divergingOption,
  lineOption,
  sparkOption,
  stackedBarsOption,
  treeOption,
  type ChartHandle,
  type ChartTheme,
} from "@charie/shared";
import {
  COST_PER_DAY,
  DELIVERY_PER_DAY,
  DROP_TREE,
  NET_SALES_SPARK,
  SALES_CHANGE,
  TOP_RESTAURANTS,
  dollarFormat,
  percentFormat,
  thousandsFormat,
} from "@charie/shared/mocks";
import { Download } from "lucide-react";
import KitSection from "./KitSection";

function Figure({
  title,
  subtitle,
  chartRef,
  children,
}: {
  title: string;
  subtitle: string;
  chartRef?: React.RefObject<ChartHandle | null>;
  children: React.ReactNode;
}) {
  return (
    <div
      data-figure={title}
      className="min-w-0 rounded-card border border-border bg-surface px-[18px] pb-3 pt-4 shadow-card"
    >
      <div className="mb-2">
        <div className="font-serif text-[17px]">{title}</div>
        <div className="mt-0.5 text-[12.5px] text-muted">{subtitle}</div>
      </div>
      {children}
      {chartRef && (
        <div className="mt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => chartRef.current?.downloadPng(title)}
            aria-label={`Download ${title} as image`}
          >
            <Download />
            Download as image
          </Button>
        </div>
      )}
    </div>
  );
}

export default function ChartsSection() {
  const divergingRef = useRef<ChartHandle>(null);
  const lineRef = useRef<ChartHandle>(null);
  const barRef = useRef<ChartHandle>(null);
  const stackedRef = useRef<ChartHandle>(null);
  const treeRef = useRef<ChartHandle>(null);

  const divergingBuild = useCallback(
    (theme: ChartTheme) => divergingOption(SALES_CHANGE, theme, percentFormat),
    [],
  );
  const lineBuild = useCallback(
    (theme: ChartTheme) => lineOption(DELIVERY_PER_DAY, theme, thousandsFormat),
    [],
  );
  const barBuild = useCallback(
    (theme: ChartTheme) => barOption(TOP_RESTAURANTS, theme, thousandsFormat),
    [],
  );
  const sparkAccentBuild = useCallback(
    (theme: ChartTheme) => sparkOption(NET_SALES_SPARK, theme.accent),
    [],
  );
  const sparkBadBuild = useCallback(
    (theme: ChartTheme) => sparkOption(NET_SALES_SPARK, theme.bad),
    [],
  );
  const stackedBuild = useCallback(
    (theme: ChartTheme) => stackedBarsOption(COST_PER_DAY, theme, dollarFormat),
    [],
  );
  const treeBuild = useCallback((theme: ChartTheme) => treeOption(DROP_TREE, theme), []);

  return (
    <KitSection id="charts" title="Charts">
      <div className="grid gap-4">
        <Figure
          title="Sales change by restaurant"
          subtitle="1–26 Oct vs 1–26 Sep · the 8 biggest gains and the 3 restaurants that fell"
          chartRef={divergingRef}
        >
          <Chart ref={divergingRef} label="Sales change by restaurant" height={360} build={divergingBuild} />
        </Figure>
        <Figure
          title="Downtown Austin: delivery orders per day"
          subtitle="October so far, compared with a normal day for that weekday"
          chartRef={lineRef}
        >
          <Chart ref={lineRef} label="Downtown Austin: delivery orders per day" height={280} build={lineBuild} />
        </Figure>
        <Figure
          title="Net sales by restaurant"
          subtitle="Top 5, 1–26 Oct"
          chartRef={barRef}
        >
          <Chart ref={barRef} label="Net sales by restaurant" height={260} build={barBuild} />
        </Figure>
        <div className="grid gap-4 min-[1000px]:grid-cols-2">
          <div className="rounded-card border border-border bg-surface px-4 pb-3 pt-[14px] shadow-card">
            <div className="text-[12.5px] font-medium text-muted">Net sales</div>
            <div className="font-serif text-[28px] font-semibold">$1.42M</div>
            <div className="mx-[-4px] mb-[-4px] mt-2 h-[34px]">
              <Chart label="Net sales sparkline" height={34} build={sparkAccentBuild} />
            </div>
          </div>
          <div className="rounded-card border border-border bg-surface px-4 pb-3 pt-[14px] shadow-card">
            <div className="text-[12.5px] font-medium text-muted">Net sales, falling</div>
            <div className="font-serif text-[28px] font-semibold">$1.42M</div>
            <div className="mx-[-4px] mb-[-4px] mt-2 h-[34px]">
              <Chart label="Net sales sparkline, falling" height={34} build={sparkBadBuild} />
            </div>
          </div>
        </div>
        <Figure
          title="Cost per day"
          subtitle="October, in US dollars"
          chartRef={stackedRef}
        >
          <Chart ref={stackedRef} label="Cost per day" height={300} build={stackedBuild} />
        </Figure>
        <Figure
          title="Downtown Austin: where the drop comes from"
          subtitle="1–26 Oct, compared with 1–26 Sep"
          chartRef={treeRef}
        >
          <div className="overflow-x-auto">
            <div className="min-w-[640px]">
              <Chart ref={treeRef} label="Downtown Austin: where the drop comes from" height={380} build={treeBuild} />
            </div>
          </div>
        </Figure>
      </div>
    </KitSection>
  );
}
