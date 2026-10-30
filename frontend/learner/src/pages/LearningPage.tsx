import { Link } from "react-router";
import { Pause, Play } from "lucide-react";
import {
  Button,
  Card,
  Page,
  PageHeader,
  toast,
  useLearning,
  usePauseLearning,
  useResumeLearning,
  type LearningRun,
} from "@charie/shared";
import { LiveFeed } from "../learning/LiveFeed";
import { PastRuns } from "../learning/PastRuns";
import { RunHeader } from "../learning/RunHeader";
import { RunStats } from "../learning/RunStats";
import { StepList } from "../learning/StepList";
import { timeAgo } from "../lib/when";

// The Learning page (P04.7): run header, stats, steps and live feed, pause
// and resume, past runs and the finished summary. Reopening shows the
// current run.
export function LearningPage() {
  const learning = useLearning();
  const pause = usePauseLearning();
  const resume = useResumeLearning();

  if (learning.isPending) {
    return (
      <Page>
        <PageHeader title="Learning" />
        <p className="text-[14px] text-muted" role="status">
          Loading learning…
        </p>
      </Page>
    );
  }
  if (learning.isError || !learning.data) {
    return (
      <Page>
        <PageHeader title="Learning" />
        <p className="text-[14px] text-muted" role="alert">
          Couldn&rsquo;t load learning.{" "}
          <button
            type="button"
            className="font-medium text-accent-ink underline-offset-2 hover:underline"
            onClick={() => void learning.refetch()}
          >
            Try again
          </button>
        </p>
      </Page>
    );
  }

  const runs = learning.data.runs;
  const live = runs[0];
  if (!live) {
    return (
      <Page>
        <PageHeader title="Learning" lead="Charie hasn't started learning yet." />
        <Button asChild variant="outline">
          <Link to="/setup?step=3">Open the setup guide</Link>
        </Button>
      </Page>
    );
  }

  const going = live.status === "running" || live.status === "paused";
  return (
    <Page>
      <PageHeader
        title="Learning"
        lead={pageLead(live)}
        actions={
          live.status === "running" ? (
            <Button
              variant="outline"
              disabled={pause.isPending}
              onClick={() =>
                pause.mutate(undefined, {
                  onSuccess: () => toast("Paused. Nothing learned so far is lost."),
                  onError: (error) => toast(error.message),
                })
              }
            >
              <Pause aria-hidden="true" className="[--icon:16px]" />
              Pause
            </Button>
          ) : live.status === "paused" ? (
            <Button
              disabled={resume.isPending}
              onClick={() =>
                resume.mutate(undefined, {
                  onSuccess: () => toast("Learning again."),
                  onError: (error) => toast(error.message),
                })
              }
            >
              <Play aria-hidden="true" className="[--icon:16px]" />
              Resume
            </Button>
          ) : live.status === "failed" ? (
            <Button
              disabled={resume.isPending}
              onClick={() =>
                resume.mutate(undefined, {
                  onSuccess: () => toast("Trying again from where it stopped."),
                  onError: (error) => toast(error.message),
                })
              }
            >
              <Play aria-hidden="true" className="[--icon:16px]" />
              Try again
            </Button>
          ) : undefined
        }
      />
      <RunHeader run={live} />
      <RunStats run={live} />
      <div className="grid items-start gap-4 min-[1100px]:grid-cols-2">
        <Card padded={false} className="p-[20px_22px]">
          <p className="card-title">Steps</p>
          <div className="mt-3">
            <StepList run={live} />
          </div>
        </Card>
        <LiveFeed runId={live.id} active={going} />
      </div>
      <h2 className="section-title">Past learning runs</h2>
      <Card padded={false} className="px-[10px] py-[6px]">
        <PastRuns runs={runs} />
      </Card>
    </Page>
  );
}

function pageLead(run: LearningRun): string {
  if (run.status === "paused") return "Learning is paused. Nothing learned so far is lost.";
  if (run.status === "failed")
    return "The last learning run stopped. Nothing learned so far is lost.";
  if (run.status === "done") {
    return `Charie finished learning ${run.finished_at !== null ? timeAgo(run.finished_at) : "recently"}.`;
  }
  if (run.kind === "refresh")
    return `Charie is learning the ${run.reason ?? "latest changes"}. It keeps answering with what it already knows until this finishes.`;
  if (run.kind === "nightly")
    return "Charie is doing its nightly check. It keeps answering with what it already knows until this finishes.";
  return "Charie is learning your business for the first time. You can close this page; it keeps going.";
}
