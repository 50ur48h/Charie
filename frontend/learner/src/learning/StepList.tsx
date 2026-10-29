import { Check } from "lucide-react";
import { cn } from "@charie/shared";
import type { LearningRun, StepProgress } from "@charie/shared";
import { LEARNING_STEPS } from "./steps";

// The 12 learning steps (P04.7): done steps get the accent circle and check,
// the current one the pulsing ring (still when the user prefers no motion),
// later ones stay muted.
export function StepList({ run }: { run: LearningRun }) {
  const finished = run.status === "done";
  return (
    <ol className="m-0 list-none p-0">
      {LEARNING_STEPS.map((step, i) => {
        const number = i + 1;
        const progress = run.progress.find((entry) => entry.step === number);
        const isDone = finished || number < run.step;
        const isCurrent = !finished && number === run.step;
        return (
          <li key={number} className={cn("relative flex gap-3 pb-4 last:pb-0")}>
            {i < LEARNING_STEPS.length - 1 && (
              <span
                aria-hidden="true"
                className={cn(
                  "absolute bottom-0.5 left-[13px] top-[30px] w-0.5",
                  isDone ? "bg-accent" : "bg-border",
                )}
              />
            )}
            <span
              aria-hidden="true"
              className={cn(
                "relative z-[1] grid size-7 flex-none place-items-center rounded-full border-2",
                isDone && "border-accent bg-accent text-white",
                isCurrent && "border-accent bg-surface motion-safe:animate-[ring_1.3s_ease-out_infinite]",
                !isDone && !isCurrent && "border-border bg-surface-2 text-muted",
              )}
            >
              {isDone ? (
                <Check className="[--icon:14px] stroke-[2.6px]" />
              ) : isCurrent ? (
                <span className="size-2.5 rounded-full bg-accent" />
              ) : null}
            </span>
            <div>
              <p
                className={cn(
                  "text-[14px] font-semibold",
                  !isDone && !isCurrent && "font-medium text-muted",
                )}
              >
                {step.label}
              </p>
              <StepNote progress={progress} current={isCurrent} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function StepNote({ progress, current }: { progress: StepProgress | undefined; current: boolean }) {
  const note = progress?.note ?? "";
  if (note === "") return null;
  return (
    <p className={cn("mt-px text-[13px] text-muted", current && "font-medium text-accent-ink")}>
      {note}
    </p>
  );
}
