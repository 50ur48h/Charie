import { Check } from "lucide-react";
import { cn } from "@charie/shared";

// The 5 setup steps, copied from the design. Numbers count from 1; the
// design's ?step= counts from 0.
export const SETUP_STEPS = [
  { n: 1, title: "Connect your database", desc: "Read-only. Charie never changes it." },
  { n: 2, title: "Add documents and notes", desc: "Word, PDF and your own notes" },
  { n: 3, title: "Let Charie learn", desc: "About 1–2 hours" },
  { n: 4, title: "Answer its questions", desc: "A few minutes" },
  { n: 5, title: "Charie is ready", desc: "Start asking questions" },
] as const;

export function SetupSteps({
  current,
  open,
  done,
  onOpen,
}: {
  current: number;
  open: number;
  done: boolean;
  onOpen: (step: number) => void;
}) {
  return (
    <nav aria-label="Setup steps" className="grid content-start gap-1 min-[1200px]:sticky min-[1200px]:top-6">
      <span className="sr-only">
        Step {open} of 5
      </span>
      {SETUP_STEPS.map((step) => {
        const finished = done || step.n < current;
        const active = step.n === open;
        return (
          <button
            key={step.n}
            type="button"
            onClick={() => onOpen(step.n)}
            aria-current={active ? "step" : undefined}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-[12px] p-[10px_8px] text-left transition-colors duration-200 hover:bg-surface-2",
              active && "bg-surface",
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "grid size-[30px] flex-none place-items-center rounded-full border-2 text-[13px] font-semibold transition-all duration-300",
                finished
                  ? "border-accent bg-accent text-white"
                  : active
                    ? "border-accent bg-surface text-accent-ink shadow-[0_0_0_4px_var(--accent-soft)]"
                    : "border-border bg-surface-2 text-muted",
              )}
            >
              {finished ? <Check className="[--icon:15px]" strokeWidth={2.6} /> : step.n}
            </span>
            <span className="grid gap-0.5">
              <span className={cn("text-[14px] font-semibold", active && "text-accent-ink")}>
                {step.title}
              </span>
              <span className="text-[12.5px] text-muted">{step.desc}</span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}
