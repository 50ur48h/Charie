import { Chart } from "../charts/Chart";
import { sparkOption } from "../charts/spark";
import type { ChartTheme } from "../theme/chartTheme";
import { StatCard } from "../components/StatCard";
import type { KpiItem, KpisBlock as KpisBlockType } from "../api/chat-types";

// Number cards. Value, change, comparison and sparkline render exactly as
// the API provides them: a missing change or spark renders nothing, never
// a placeholder. Direction is already encoded in the change's sign.
function KpiCard({ item }: { item: KpiItem }) {
  const foot =
    item.change === undefined
      ? undefined
      : item.compare === undefined
        ? item.change
        : `${item.change} ${item.compare}`;
  return (
    <StatCard label={item.label} value={item.value} foot={foot}>
      {item.spark !== undefined && (
        <div className="mx-[-4px] mb-[-4px] mt-2 h-[34px]">
          <Chart
            label={`${item.label} trend`}
            height={34}
            build={(theme: ChartTheme) => sparkOption(item.spark?.values ?? [], theme.accent)}
          />
        </div>
      )}
    </StatCard>
  );
}

export function KpisBlock({ block }: { block: KpisBlockType }) {
  return (
    <div className="mb-4 grid grid-cols-2 gap-3 min-[900px]:grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
      {block.items.map((item) => (
        <KpiCard key={item.label} item={item} />
      ))}
    </div>
  );
}
