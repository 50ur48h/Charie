import { useState } from "react";
import { useNavigate } from "react-router";
import { Check } from "lucide-react";
import {
  Button,
  Card,
  IconBox,
  Page,
  PageHeader,
  QuestionCard,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  toast,
  useAnswerQuestion,
  useQuestions,
  useSkipQuestion,
  type OwnerQuestion,
  type QuestionStatus,
} from "@charie/shared";

function AnsweredRow({
  question,
  onChange,
}: {
  question: OwnerQuestion;
  onChange: () => void;
}) {
  const label =
    question.answer?.text ??
    question.options.find((o) => o.id === question.answer?.optionId)?.label ??
    "Answered";
  return (
    <div className="flex items-center gap-3 rounded-[14px] border border-border bg-surface p-[12px_16px]">
      <IconBox icon={Check} />
      <div className="min-w-0">
        <div className="text-[14px] font-medium">{question.title}</div>
        <div className="truncate text-[13px] text-muted">{label}</div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="ml-auto flex-none"
        onClick={onChange}
        aria-label={`Change your answer to ${question.title}`}
      >
        Change
      </Button>
    </div>
  );
}

const TABS: { value: QuestionStatus; label: string; empty: string }[] = [
  { value: "waiting", label: "Waiting", empty: "Nothing waiting. Charie will ask here when it finds something only you can answer." },
  { value: "answered", label: "Answered", empty: "No answers yet." },
  { value: "skipped", label: "Skipped", empty: "Nothing skipped." },
];

export function QuestionsPage() {
  const navigate = useNavigate();
  const waiting = useQuestions("waiting");
  const answered = useQuestions("answered");
  const skipped = useQuestions("skipped");
  const answer = useAnswerQuestion();
  const skip = useSkipQuestion();
  const [editing, setEditing] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const counts: Record<QuestionStatus, number | undefined> = {
    waiting: waiting.data?.questions.length,
    answered: answered.data?.questions.length,
    skipped: skipped.data?.questions.length,
  };
  const queries = { waiting, answered, skipped };
  const failed = TABS.find((tab) => queries[tab.value].isError);
  const loading = TABS.some((tab) => queries[tab.value].isPending);

  function askAbout(question: OwnerQuestion): void {
    navigate(`/?draft=${encodeURIComponent(`Help me decide: ${question.title}`)}`);
  }

  return (
    <Page narrow>
      <PageHeader
        title="Questions for you"
        lead="While learning, Charie found a few things only you can answer. Each takes under a minute. If you skip one, Charie uses the default shown and says so in its answers."
      />
      {failed ? (
        <Card padded role="alert">
          <p className="text-[14px]">Couldn&apos;t load your questions.</p>
          <Button
            variant="ghost"
            className="mt-2"
            onClick={() => void queries[failed.value].refetch()}
          >
            Try again
          </Button>
        </Card>
      ) : (
        <Tabs defaultValue="waiting">
          <TabsList aria-label="Question states">
            {TABS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value} count={counts[tab.value]}>
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
          {TABS.map((tab) => {
            const list = queries[tab.value].data?.questions ?? [];
            return (
              <TabsContent key={tab.value} value={tab.value} className="mt-4">
                {loading ? (
                  <Card padded>
                    <p className="text-[14px] text-muted" role="status">
                      Loading questions…
                    </p>
                  </Card>
                ) : list.length === 0 ? (
                  <Card padded>
                    <p className="text-[14px] text-muted">{tab.empty}</p>
                  </Card>
                ) : tab.value === "waiting" ? (
                  <div className="grid gap-4">
                    {list.map((question) => (
                      <QuestionCard
                        key={question.id}
                        question={question}
                        saving={answer.isPending && editing === null}
                        saveError={saveError}
                        onSave={(selection) => {
                          setSaveError(null);
                          const payload =
                            "optionId" in selection
                              ? { optionId: selection.optionId }
                              : { text: selection.text };
                          answer.mutate(
                            { questionId: question.id, answer: payload },
                            {
                              onSuccess: () =>
                                toast("Saved. Charie is re-checking what this affects."),
                              onError: () =>
                                setSaveError("Couldn't save that answer. Try again."),
                            },
                          );
                        }}
                        onSkip={() => skip.mutate(question.id)}
                        onAskAbout={() => askAbout(question)}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="grid gap-2">
                    {list.map((question) =>
                      editing === question.id ? (
                        <QuestionCard
                          key={question.id}
                          question={question}
                          showSkip={false}
                          saving={answer.isPending}
                          onCancel={() => {
                            setEditing(null);
                            setSaveError(null);
                          }}
                          saveError={saveError}
                          onSave={(selection) => {
                            setSaveError(null);
                            const payload =
                              "optionId" in selection
                                ? { optionId: selection.optionId }
                                : { text: selection.text };
                            const saved = question.answer;
                            const previous =
                              saved?.optionId !== undefined
                                ? { optionId: saved.optionId }
                                : saved?.text !== undefined
                                  ? { text: saved.text }
                                  : undefined;
                            answer.mutate(
                              { questionId: question.id, answer: payload, previous },
                              {
                                onSuccess: () => {
                                  setEditing(null);
                                  toast("Saved. Charie is re-checking what this affects.");
                                },
                                onError: () =>
                                  setSaveError("Couldn't save that answer. Try again."),
                              },
                            );
                          }}
                          onSkip={() => setEditing(null)}
                          onAskAbout={() => askAbout(question)}
                        />
                      ) : (
                        <AnsweredRow
                          key={question.id}
                          question={question}
                          onChange={() => {
                            setEditing(question.id);
                            setSaveError(null);
                          }}
                        />
                      ),
                    )}
                  </div>
                )}
              </TabsContent>
            );
          })}
        </Tabs>
      )}
    </Page>
  );
}
