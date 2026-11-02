// The "still learning" card on the New chat page (P12.1): asking is refused
// before the first published knowledge version, so the ideas make way for
// this card and the question box stays disabled.
import { ArrowUpRight, GraduationCap } from "lucide-react";
import { Button, Card, IconBox, Progress } from "@charie/shared";
import type { StatusLearning } from "@charie/shared";

export function StillLearning({
  learning,
  learnerUrl,
}: {
  learning: StatusLearning | null;
  learnerUrl: string | null;
}) {
  const status = learning?.status ?? "none";
  const stepTitle = learning?.step_title ?? null;
  const percent = learning?.percent ?? 0;

  return (
    <Card padded>
      <div className="flex items-center gap-3.5">
        <IconBox icon={GraduationCap} />
        <h2 className="card-title">Charie is still learning</h2>
      </div>
      <p className="mt-2 text-[14px] text-muted">
        It&apos;s studying your database and documents. You can ask questions once the first version
        of its knowledge is published in the Learner.
      </p>
      <div className="mt-3">
        {status === "running" ? (
          <div>
            <Progress label={`Learning progress: ${percent} percent`} value={percent} />
            <p className="mt-1.5 text-[13px] text-muted" role="status">
              {stepTitle ? `${percent}% · ${stepTitle}` : `${percent}%`}
            </p>
          </div>
        ) : status === "paused" ? (
          <p className="text-[13px] text-muted" role="status">
            {stepTitle ? `Paused at ${percent}% · ${stepTitle}` : `Paused at ${percent}%`}
          </p>
        ) : status === "failed" ? (
          <p className="text-[13px] text-muted" role="status">
            The last learning run stopped with a problem. Open the Learner to see what happened.
          </p>
        ) : status === "done" ? (
          <p className="text-[13px] text-muted" role="status">
            Learning is done. Publish the first version in the Learner to start.
          </p>
        ) : (
          <p className="text-[13px] text-muted" role="status">
            Learning hasn&apos;t started yet.
          </p>
        )}
      </div>
      {learnerUrl && (
        <Button variant="outline" size="sm" className="mt-3" asChild>
          <a href={learnerUrl} target="_blank" rel="noreferrer">
            Open Learner
            <ArrowUpRight aria-hidden="true" />
          </a>
        </Button>
      )}
    </Card>
  );
}
