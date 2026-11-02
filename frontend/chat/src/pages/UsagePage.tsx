import { useState } from "react";
import { useSearchParams } from "react-router";
import { Brain } from "lucide-react";
import {
  Button,
  Card,
  Chart,
  Page,
  PageHeader,
  Pill,
  Progress,
  SpendingLimitsDialog,
  StatCard,

  stackedBarsOption,
  useBudgetSettings,
  useUpdateBudgetSettings,
  useUsage,
  type TopQuestion,
  type UsageSummary,
} from "@charie/shared";
import { chatRoutes, RouterLink } from "@charie/shared";

function money(n: number, decimals = 2): string {
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

function CostPerDayChart({ usage }: { usage: UsageSummary }) {
  return (
    <Chart
      label="What each day cost"
      height={200}
      build={(theme) =>
        stackedBarsOption(
          {
            labels: usage.per_day.map((d) => d.date),
            series: [
              { name: "Questions", values: usage.per_day.map((d) => d.questions_usd) },
              { name: "Learning", values: usage.per_day.map((d) => d.learning_usd) },
              { name: "Tests", values: usage.per_day.map((d) => d.tests_usd) },
            ],
            labelEvery: Math.max(1, Math.floor(usage.per_day.length / 8)),
          },
          theme,
          {
            axis: (v) => `$${v}`,
            tooltip: (v) => money(v),
          },
        )
      }
    />
  );
}

function TopQuestionsTable({ rows }: { rows: TopQuestion[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="overflow-x-auto" role="region" aria-label="Most expensive questions">
      <table className="w-full min-w-[640px] text-[13.5px]">
        <thead>
          <tr className="border-b border-border text-left text-[12px] uppercase tracking-wide text-muted">
            <th className="py-2 pr-3 font-semibold">Question</th>
            <th className="py-2 pr-3 font-semibold">Chat</th>
            <th className="py-2 pr-3 text-right font-semibold">Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.message_id} className="border-b border-border last:border-0">
              <th scope="row" className="py-2.5 pr-3 text-left font-normal">
                <RouterLink
                  className="text-accent-ink underline-offset-2 hover:underline"
                  to={chatRoutes.chat(row.chat_id)}
                >
                  {row.question}
                </RouterLink>
                <span className="mt-0.5 block text-[12.5px] text-muted">
                  {row.seconds}s · {row.steps} steps
                </span>
              </th>
              <td className="py-2.5 pr-3">
                <RouterLink
                  className="text-accent-ink underline-offset-2 hover:underline"
                  to={chatRoutes.chat(row.chat_id)}
                  aria-label={`Open chat for ${row.question}`}
                >
                  Open
                </RouterLink>
              </td>
              <td className="py-2.5 text-right tabular-nums">{money(row.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function thisMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function modelLabel(model: string): string {
  return `Model: ${model === "muse-wonder-1.0" ? "Muse Wonder" : model}`;
}

export function UsagePage() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") ?? undefined;
  const usage = useUsage(month);
  const budget = useBudgetSettings();
  const updateBudget = useUpdateBudgetSettings();
  const [managing, setManaging] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const data = usage.data;
  const failed = usage.isError;

  return (
    <Page>
      <PageHeader
        title="Usage"
        lead="What Charie's AI has cost this month. Every number here comes from the log of each AI call."
        actions={
          <div className="flex items-center gap-2">
            {data && <Pill icon={Brain}>{modelLabel(data.model)}</Pill>}
            <label className="text-[13px] text-muted" htmlFor="usage-month">
              Month
            </label>
            <input
              id="usage-month"
              type="month"
              className="rounded-[10px] border border-border bg-surface px-2.5 py-1.5 text-[13.5px]"
              value={month ?? thisMonth()}
              max={thisMonth()}
              onChange={(event) => {
                const next = event.target.value;
                setParams(next && next !== thisMonth() ? { month: next } : {}, { replace: true });
              }}
            />
          </div>
        }
      />
      {failed ? (
        <Card padded role="alert">
          <p className="text-[14px]">Couldn&apos;t load usage. Use a month like 2026-10.</p>
          <Button variant="ghost" className="mt-2" onClick={() => void usage.refetch()}>
            Try again
          </Button>
        </Card>
      ) : data ? (
        <div className="grid gap-4">
          <Card padded aria-label={`Budget: ${money(data.spent_usd)} of ${money(data.limit_usd)}`}>
            <div className="flex flex-wrap items-baseline gap-x-3">
              <span className="font-serif text-[26px] font-semibold tabular-nums">
                {money(data.spent_usd)}
              </span>
              <span className="text-[14px] text-muted">of {money(data.limit_usd)} monthly credit</span>
              <Button
                variant="outline"
                size="sm"
                className="ml-auto"
                onClick={() => {
                  setSaveError(null);
                  setManaging(true);
                }}
              >
                Spending limits
              </Button>
            </div>
            <Progress
              className="mt-3"
              label={`Used ${Math.round(data.percent_used)} percent of the monthly credit`}
              value={Math.min(100, data.percent_used)}
            />
            <p className="mt-2 text-[13px] text-muted">
              {data.state === "paused"
                ? `Over the limit. New questions resume ${data.resets_on}.`
                : `About ${money(data.expected_usd)} by ${data.resets_on} at this pace.`}
            </p>
          </Card>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Questions answered" value={String(data.questions.count)} foot={`About ${money(data.questions.cost_usd / Math.max(1, data.questions.count))} each`} />
            <StatCard label="Learning runs" value={String(data.learning_runs.count)} foot={`${money(data.learning_runs.cost_usd)} total`} />
            <StatCard label="Resets on" value={data.resets_on} foot={`${data.days_in_month} days this month`} />
            <StatCard label="Expected by reset" value={money(data.expected_usd)} foot={`${Math.round(data.percent_used)}% of credit used`} />
          </div>
          <Card padded aria-label="What each day cost">
            <h2 className="card-title">What each day cost</h2>
            <div className="mt-2">
              <CostPerDayChart usage={data} />
            </div>
          </Card>
          <Card padded aria-label="Where the money goes">
            <h2 className="card-title">Where the money goes</h2>
            {data.per_group.length === 0 ? (
              <p className="mt-2 text-[14px] text-muted">Nothing spent this month yet.</p>
            ) : (
              <div className="mt-3 grid gap-2.5">
                {data.per_group.map((group) => (
                  <div key={group.group}>
                    <div className="flex items-baseline justify-between text-[13.5px]">
                      <span>{group.group}</span>
                      <span className="tabular-nums text-muted">
                        {money(group.cost_usd)} · {group.percent}%
                      </span>
                    </div>
                    <Progress label={`${group.group}: ${money(group.cost_usd)}`} value={group.percent} thin />
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card padded aria-label="Most expensive questions">
            <h2 className="card-title">Most expensive questions</h2>
            {data.top_questions.length === 0 ? (
              <p className="mt-2 text-[14px] text-muted">No questions this month yet.</p>
            ) : (
              <div className="mt-1">
                <TopQuestionsTable rows={data.top_questions} />
              </div>
            )}
          </Card>
        </div>
      ) : (
        <Card padded>
          <p className="text-[14px] text-muted" role="status">
            Loading usage…
          </p>
        </Card>
      )}
      {managing && budget.data && (
        <SpendingLimitsDialog
          limitUsd={budget.data.spend_limit_usd}
          warnPercent={budget.data.spend_warn_percent}
          saving={updateBudget.isPending}
          serverError={saveError}
          onSave={(patch) => {
            setSaveError(null);
            updateBudget.mutate(patch, {
              onSuccess: () => setManaging(false),
              onError: (error) => setSaveError(error.message),
            });
          }}
          onClose={() => {
            setManaging(false);
            setSaveError(null);
          }}
        />
      )}
    </Page>
  );
}
