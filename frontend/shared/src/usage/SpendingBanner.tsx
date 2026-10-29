import { CircleAlert } from "lucide-react";
import { Button } from "../components/Button";
import type { Spending } from "../api/usage";

function money(n: number): string {
  return `$${n.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

// Shared by the New chat page and Usage: warning and paused states from
// GET /api/status (P05.9 shapes). Paused blocks new questions in the mock.
export function SpendingBanner({
  spending,
  onManage,
}: {
  spending: Spending;
  onManage: () => void;
}) {
  if (spending.state === "ok") return null;
  const paused = spending.state === "paused";
  return (
    <div
      role={paused ? "alert" : "status"}
      className={
        paused
          ? "m-4 rounded-card border border-bad bg-bad-soft p-4"
          : "m-4 rounded-card border border-warn bg-warn-soft p-4"
      }
    >
      <div className="flex flex-wrap items-center gap-3">
        <CircleAlert
          aria-hidden="true"
          className={paused ? "text-bad-ink [--icon:20px]" : "text-warn-ink [--icon:20px]"}
        />
        <p className="min-w-0 flex-1 text-[14px]">
          {paused ? (
            <>
              <b>Questions are paused.</b> You&apos;ve used {money(spending.spent_usd)} of your{" "}
              {money(spending.limit_usd)} monthly credit. Raise the limit to keep asking.
            </>
          ) : (
            <>
              <b>You&apos;ve used {Math.round(spending.percent_used)}% of your credit.</b>{" "}
              {money(spending.spent_usd)} of {money(spending.limit_usd)} so far this month.
            </>
          )}
        </p>
        <Button variant={paused ? "primary" : "outline"} size="sm" onClick={onManage}>
          {paused ? "Raise limit" : "Spending limits"}
        </Button>
      </div>
    </div>
  );
}
