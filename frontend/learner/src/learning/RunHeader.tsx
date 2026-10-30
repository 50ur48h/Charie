import { Link } from "react-router";
import { Button, Card, Pill, Progress, StatusDot, type LearningRun } from "@charie/shared";
import { LEARNING_STEPS } from "./steps";
import { clockTime, howLong } from "../lib/when";

// The run header (P04.7): big percent and status pill, the plain-English
// line, the progress bar, and the step line. Cost always has 2 decimals.
export function RunHeader({ run }: { run: LearningRun }) {
  const started = clockTime(run.started_at);
  const cost = `$${run.cost_usd.toFixed(2)}`;
  return (
    <Card padded={false} className="mb-4 flex flex-wrap items-center gap-5 p-[22px_24px]">
      <p className="min-w-[92px] font-serif text-[40px] font-semibold leading-none tabular-nums">
        {run.percent}%
      </p>
      <div className="min-w-[240px] flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <RunPill run={run} />
          <span className="text-[13px] text-muted">
            <RunLine run={run} started={started} cost={cost} />
          </span>
        </p>
        <Progress value={run.percent} max={100} label="Learning progress" className="my-2 h-[10px]" />
        <RunStepLine run={run} />
      </div>
    </Card>
  );
}

function RunPill({ run }: { run: LearningRun }) {
  if (run.status === "running") {
    return (
      <Pill tone="good">
        <StatusDot tone="good" />
        Learning now
      </Pill>
    );
  }
  if (run.status === "paused") {
    return <Pill tone="warn">Paused</Pill>;
  }
  if (run.status === "done") {
    return (
      <Pill tone="accent">
        <StatusDot tone="good" />
        Finished
      </Pill>
    );
  }
  return <Pill tone="bad">Stopped</Pill>;
}

function RunLine({ run, started, cost }: { run: LearningRun; started: string; cost: string }) {
  if (run.status === "running") {
    const minutes = run.minutes_left;
    // Unknown remaining time stays honest: never synthesize an estimate.
    const left =
      minutes === null ? <>Working on it</> : minutes >= 90 ? (
        <>about {Math.max(1, Math.round(minutes / 60))} hours left</>
      ) : (
        <>about {minutes} minutes left</>
      );
    return (
      <>
        Started {started} {" "}· {left} {" "}· {cost} so far
      </>
    );
  }
  if (run.status === "paused") {
    return (
      <>
        Started {started} · paused · {cost} so far
      </>
    );
  }
  if (run.status === "done" && run.finished_at !== null) {
    return (
      <>
        Started {started} · took {howLong(run.started_at, run.finished_at)} · {cost}
      </>
    );
  }
  return <>Started {started} · {cost}</>;
}

function RunStepLine({ run }: { run: LearningRun }) {
  // Position among the run's actual steps, not the canonical twelve.
  const total = run.progress.length;
  const position = run.progress.findIndex((entry) => entry.step === run.step);
  const shown = position === -1 ? run.step : position + 1;
  const phrase = LEARNING_STEPS[run.step - 1]?.phrase ?? "";
  if (run.status === "done") {
    return (
      <p className="text-[13px] text-muted">
        {total === 0 ? run.summary : <>All {total} steps done · {run.summary}</>}{" "}
        <Button asChild variant="outline" size="sm" className="ml-2">
          <Link to="/knowledge">Review in Knowledge</Link>
        </Button>
      </p>
    );
  }
  if (total === 0) return null;
  if (run.status === "failed") {
    return (
      <p className="text-[13px] text-muted">
        Stopped at step {shown} of {total}: {phrase}
      </p>
    );
  }
  return (
    <p className="text-[13px] text-muted">
      Step {shown} of {total}: {phrase}
    </p>
  );
}
