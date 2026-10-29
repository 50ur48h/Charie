import { useState } from "react";
import { ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Check, Database, Hash } from "lucide-react";
import {
  Button,
  Card,
  IconBox,
  Pill,
  QuestionCard,
  toast,
  useAnswerQuestion,
  useQuestions,
  useSkipQuestion,
  type AnswerPayload,
  type OwnerQuestion,
} from "@charie/shared";
import { useChatUrl } from "../layout/useChatUrl";

// Step 4: the waiting owner questions, one row each. A row opens P03.10's
// QuestionCard under it (one at a time); saving or skipping removes the row.
// With none waiting, the "All caught up" card shows instead.
const TOPIC_ICONS = { "Business word": BookOpen, Data: Database, Codes: Hash } as const;

function TopicIcon({ topic }: { topic: string }) {
  const Icon = (TOPIC_ICONS as Record<string, typeof BookOpen>)[topic] ?? BookOpen;
  return <IconBox icon={Icon} tone="plain" size={34} />;
}

export function QuestionsStep({ onBack, onNext }: { onBack: () => void; onNext: () => void }) {
  const waiting = useQuestions("waiting");
  const answer = useAnswerQuestion();
  const skip = useSkipQuestion();
  const chatUrl = useChatUrl();
  const [openId, setOpenId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const list = waiting.data?.questions ?? [];

  function save(question: OwnerQuestion, selection: AnswerPayload): void {
    setSaveError(null);
    answer.mutate(
      { questionId: question.id, answer: selection },
      {
        onSuccess: () => {
          setOpenId(null);
          toast("Saved. Charie is re-checking what this affects.");
        },
        onError: () => setSaveError("Couldn't save that answer. Try again."),
      },
    );
  }

  return (
    <section aria-label="Answer its questions">
      <h2 className="font-serif text-[24px] font-semibold">Answer its questions</h2>
      {waiting.isPending ? (
        <p className="mt-1.5 text-[14.5px] text-muted" role="status">
          Loading Charie&rsquo;s questions…
        </p>
      ) : waiting.isError ? (
        <Card padded role="alert" className="mt-4">
          <p className="text-[14px]">Couldn&rsquo;t load Charie&rsquo;s questions.</p>
          <Button variant="ghost" className="mt-2" onClick={() => void waiting.refetch()}>
            Try again
          </Button>
        </Card>
      ) : list.length === 0 ? (
        <div className="mt-4 grid justify-items-center gap-1 rounded-[14px] border border-border bg-surface-2 p-8 text-center">
          <IconBox icon={Check} tone="good" size={44} />
          <p className="mt-2 text-[16px] font-semibold">All caught up</p>
          <p className="max-w-[420px] text-[14px] text-muted">
            Charie is re-checking everything your answers affect. You&rsquo;ll see the
            results in Knowledge.
          </p>
        </div>
      ) : (
        <>
          <p className="mt-1.5 text-[14.5px] text-muted">
            Charie found {list.length === 1 ? "1 thing" : `${list.length} things`} only
            you can answer. Each takes under a minute, and each shows the number every
            choice would give.
          </p>
          <div className="mt-3.5 grid gap-2">
            {list.map((question) => (
              <div key={question.id} className="grid gap-2">
                <button
                  type="button"
                  aria-expanded={openId === question.id}
                  onClick={() => {
                    setOpenId((open) => (open === question.id ? null : question.id));
                    setSaveError(null);
                  }}
                  className="flex w-full cursor-pointer items-center gap-3 rounded-[12px] bg-surface-2 p-[10px_14px] text-left text-[14px] transition-colors duration-200 hover:bg-[color-mix(in_srgb,var(--accent-soft)_35%,var(--surface-2))]"
                >
                  <TopicIcon topic={question.topic} />
                  <span className="min-w-0 flex-1 truncate font-medium">{question.title}</span>
                  <Pill tone="outline">{question.importance}</Pill>
                </button>
                {openId === question.id && (
                  <QuestionCard
                    question={question}
                    saving={answer.isPending || skip.isPending}
                    saveError={saveError}
                    onSave={(selection) => save(question, selection)}
                    onSkip={() => {
                      setSaveError(null);
                      skip.mutate(question.id, { onSuccess: () => setOpenId(null) });
                    }}
                  />
                )}
              </div>
            ))}
          </div>
        </>
      )}
      <div className="mt-6 flex flex-wrap gap-2.5 border-t border-border-soft pt-[18px]">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft aria-hidden="true" className="[--icon:16px]" />
          Back
        </Button>
        {chatUrl !== null && (
          <Button variant="outline" asChild>
            <a href={`${chatUrl}/questions`} target="_blank" rel="noreferrer">
              Answer in Charie
              <ArrowUpRight aria-hidden="true" className="[--icon:16px]" />
            </a>
          </Button>
        )}
        <Button className="ml-auto max-[640px]:ml-0 max-[640px]:w-full" onClick={onNext}>
          Continue
          <ArrowRight aria-hidden="true" className="[--icon:16px]" />
        </Button>
      </div>
    </section>
  );
}
