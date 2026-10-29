import { useState } from "react";
import { Info } from "lucide-react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Pill } from "../components/Pill";
import { QuestionEvidence } from "./QuestionEvidence";
import { initialSelection, QuestionOptions, savedSelection, type OptionSelection } from "./QuestionOptions";
import type { OwnerQuestion } from "./types";

function answerLabel(question: OwnerQuestion): string | null {
  if (!question.answer) return null;
  if (question.answer.text !== undefined) return question.answer.text;
  return question.options.find((o) => o.id === question.answer?.optionId)?.label ?? null;
}

// One question card: title, evidence, options, default and Save/Skip.
// Selecting never saves; the parent saves and only unmounts on success,
// so a failed save keeps the selection.
export function QuestionCard({
  question,
  saving = false,
  saveError = null,
  showSkip = true,
  onSave,
  onSkip,
  onCancel,
  onAskAbout,
}: {
  question: OwnerQuestion;
  saving?: boolean;
  saveError?: string | null;
  showSkip?: boolean;
  onSave: (selection: OptionSelection) => void;
  onSkip: () => void;
  onCancel?: () => void;
  onAskAbout?: () => void;
}) {
  // Change starts from the saved answer (option or free text); the
  // documented default applies only when nothing is saved yet.
  const [selection, setSelection] = useState<OptionSelection | null>(() =>
    savedSelection(question) ?? initialSelection(question.options, question.defaultOption),
  );
  const [blank, setBlank] = useState(false);
  const answered = answerLabel(question);

  function save(): void {
    if (selection === null) {
      setBlank(true);
      return;
    }
    if ("text" in selection && selection.text.trim() === "") {
      setBlank(true);
      return;
    }
    setBlank(false);
    onSave("text" in selection ? { text: selection.text.trim() } : selection);
  }

  return (
    <section aria-label={question.title}>
    <Card padded>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="accent">{question.topic}</Pill>
        {question.importance && <Pill tone="outline">{question.importance}</Pill>}
      </div>
      <h2 className="mt-2.5 font-serif text-[22px] font-semibold leading-[1.3]">{question.title}</h2>
      {question.body && <p className="mt-1.5 text-[14px] text-text-2">{question.body}</p>}
      <QuestionEvidence evidence={question.evidence} />
      {answered !== null && (
        <p className="mt-3 text-[13.5px] text-muted">
          Your answer: <b className="text-text">{answered}</b>
        </p>
      )}
      <div className="mt-3">
        <QuestionOptions
          options={question.options}
          allowText={question.allowText}
          value={selection}
          initialText={question.answer?.text}
          onChange={(next) => {
            setSelection(next);
            setBlank(false);
          }}
        />
      </div>
      {question.defaultReason && question.status === "waiting" && (
        <p className="mt-3 flex items-start gap-2 text-[13px] text-muted">
          <Info aria-hidden="true" className="mt-px flex-none [--icon:15px] text-accent" />
          <span>{question.defaultReason}</span>
        </p>
      )}
      {(blank || saveError) && (
        <p role="alert" className="mt-2.5 text-[13px] text-bad-ink">
          {blank ? "Pick an option or write your answer first." : saveError}
        </p>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save answer"}
        </Button>
        {showSkip && (
          <Button variant="ghost" onClick={onSkip} disabled={saving}>
            Skip for now
          </Button>
        )}
        {onCancel && (
          <Button variant="ghost" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
        )}
        {onAskAbout && (
          <button type="button" onClick={onAskAbout} className="ml-auto text-[13px] font-medium text-accent-ink underline-offset-2 hover:underline">
            Ask Charie about this
          </button>
        )}
      </div>
    </Card>
    </section>
  );
}
