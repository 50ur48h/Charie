import { StatCard, type LearningRun } from "@charie/shared";

// The 4 stat cards (P04.7): each shows one step's done over its total.
// Steps without a total show just the done count.
export function RunStats({ run }: { run: LearningRun }) {
  const stats: { label: string; value: string }[] = [
    { label: "Tables studied", value: stepValue(run, 2) },
    { label: "Documents read", value: stepValue(run, 5) },
    { label: "Facts found", value: stepValue(run, 6) },
    { label: "Questions for you", value: stepValue(run, 10) },
  ];
  return (
    <div className="mb-4 grid gap-4 grid-cols-2 min-[1000px]:grid-cols-4">
      {stats.map((stat) => (
        <StatCard key={stat.label} label={stat.label} value={stat.value} />
      ))}
    </div>
  );
}

function stepValue(run: LearningRun, step: number): string {
  const found = run.progress.find((entry) => entry.step === step);
  if (!found) return "—";
  return found.total === null ? String(found.done) : `${found.done} / ${found.total}`;
}
