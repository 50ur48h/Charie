import { useNavigate } from "react-router";
import { ArrowLeft, ArrowRight, Brain, Play } from "lucide-react";
import {
  Button,
  toast,
  useDatabaseSource,
  useDocuments,
  useLearning,
  useOwnerNotes,
  useStartLearning,
  type LearningRun,
} from "@charie/shared";
import { shortDate } from "../lib/when";

// Step 3: start the first learning run, or follow the one that's there.
// The box follows the newest `first` run: none (ready), running/paused
// (progress), done (finished) or failed (stopped).
export function LearnStep({ onBack, onNext }: { onBack: () => void; onNext: () => void }) {
  const navigate = useNavigate();
  const learning = useLearning();
  const database = useDatabaseSource();
  const documents = useDocuments();
  const notes = useOwnerNotes();
  const start = useStartLearning();

  const run: LearningRun | undefined = (learning.data?.runs ?? []).find(
    (candidate) => candidate.kind === "first",
  );

  function startLearning(): void {
    start.mutate(undefined, {
      onSuccess: () => navigate("/learning"),
      onError: (error) => toast(error.message),
    });
  }

  return (
    <section aria-label="Let Charie learn">
      <h2 className="font-serif text-[24px] font-semibold">Let Charie learn</h2>
      <p className="mt-1.5 text-[14.5px] text-muted">
        Charie studies every table and document, works out what your business words mean,
        and tests each one against the data. You can close this page; it keeps going.
      </p>
      <div className="mt-5">
        {learning.isPending ? (
          <p className="text-[14px] text-muted" role="status">
            Loading the learning progress…
          </p>
        ) : learning.isError ? (
          <p className="text-[14px] text-muted" role="alert">
            Couldn&rsquo;t load the learning progress.{" "}
            <button
              type="button"
              className="font-medium text-accent-ink underline-offset-2 hover:underline"
              onClick={() => void learning.refetch()}
            >
              Try again
            </button>
          </p>
        ) : run === undefined ? (
          <ReadyBox
            tables={database.data?.details.tables}
            documents={(documents.data?.documents ?? []).length}
            notesSaved={(notes.data?.text ?? "").trim() !== ""}
            starting={start.isPending}
            onStart={startLearning}
          />
        ) : run.status === "running" || run.status === "paused" ? (
          <div className="grid place-items-center gap-3 rounded-[18px] bg-[color-mix(in_srgb,var(--accent-soft)_55%,var(--surface))] p-[34px] text-center">
            <Brain aria-hidden="true" className="text-accent-ink [--icon:52px]" />
            <b className="font-serif text-[20px]">Charie is learning</b>
            <span className="text-[13.5px] text-muted">
              {run.percent}% done · step {run.step} of 12
            </span>
            <Button variant="primary" size="lg" onClick={() => navigate("/learning")}>
              See progress
              <ArrowRight aria-hidden="true" className="[--icon:16px]" />
            </Button>
          </div>
        ) : run.status === "done" ? (
          <div className="grid place-items-center gap-3 rounded-[18px] bg-[color-mix(in_srgb,var(--accent-soft)_55%,var(--surface))] p-[34px] text-center">
            <Brain aria-hidden="true" className="text-accent-ink [--icon:52px]" />
            <b className="font-serif text-[20px]">Charie has learned your business</b>
            <span className="text-[13.5px] text-muted">
              Finished {shortDate(run.finished_at ?? run.started_at)}
            </span>
            <Button variant="primary" size="lg" onClick={() => navigate("/knowledge")}>
              See what it learned
              <ArrowRight aria-hidden="true" className="[--icon:16px]" />
            </Button>
          </div>
        ) : (
          <div className="grid place-items-center gap-3 rounded-[18px] bg-[color-mix(in_srgb,var(--accent-soft)_55%,var(--surface))] p-[34px] text-center">
            <Brain aria-hidden="true" className="text-accent-ink [--icon:52px]" />
            <b className="font-serif text-[20px]">Learning stopped</b>
            <span className="text-[13.5px] text-muted">
              Something went wrong. Start it again.
            </span>
            <Button variant="primary" size="lg" disabled={start.isPending} onClick={startLearning}>
              <Play aria-hidden="true" className="[--icon:16px]" />
              {start.isPending ? "Starting…" : "Start learning"}
            </Button>
          </div>
        )}
      </div>
      <div className="mt-6 flex flex-wrap gap-2.5 border-t border-border-soft pt-[18px]">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft aria-hidden="true" className="[--icon:16px]" />
          Back
        </Button>
        <Button className="ml-auto max-[640px]:ml-0 max-[640px]:w-full" onClick={onNext}>
          Continue
          <ArrowRight aria-hidden="true" className="[--icon:16px]" />
        </Button>
      </div>
    </section>
  );
}

function ReadyBox({
  tables,
  documents,
  notesSaved,
  starting,
  onStart,
}: {
  tables: number | undefined;
  documents: number;
  notesSaved: boolean;
  starting: boolean;
  onStart: () => void;
}) {
  const bits = [
    tables !== undefined
      ? `${tables} ${tables === 1 ? "table" : "tables"}`
      : null,
    `${documents} ${documents === 1 ? "document" : "documents"}`,
    notesSaved ? "your notes" : null,
    "about 1–2 hours",
  ].filter((bit): bit is string => bit !== null);
  return (
    <div className="grid place-items-center gap-3 rounded-[18px] bg-[color-mix(in_srgb,var(--accent-soft)_55%,var(--surface))] p-[34px] text-center">
      <Brain aria-hidden="true" className="text-accent-ink [--icon:52px]" />
      <b className="font-serif text-[20px]">Ready to learn</b>
      <span className="text-[13.5px] text-muted">{bits.join(" · ")}</span>
      <Button variant="primary" size="lg" disabled={starting} onClick={onStart}>
        <Play aria-hidden="true" className="[--icon:16px]" />
        {starting ? "Starting…" : "Start learning"}
      </Button>
    </div>
  );
}
