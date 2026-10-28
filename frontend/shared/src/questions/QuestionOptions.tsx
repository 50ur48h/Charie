import { useState } from "react";
import { ChoiceGroup, ChoiceCard } from "../components/ChoiceCard";
import { Input } from "../components/Input";
import type { QuestionOption } from "./types";

export type OptionSelection = { optionId: string } | { text: string };

// One question's answer picker. Picking only selects; the parent saves.
// When allowText names an option, picking it reveals a free-text box and the
// save sends the trimmed text instead of the option id.
export function QuestionOptions({
  options,
  allowText,
  value,
  onChange,
}: {
  options: QuestionOption[];
  allowText?: string;
  value: OptionSelection | null;
  onChange: (selection: OptionSelection | null) => void;
}) {
  const [draft, setDraft] = useState("");
  const radioValue =
    value === null ? undefined : "optionId" in value ? value.optionId : allowText;
  return (
    <div>
      <ChoiceGroup
        value={radioValue}
        onValueChange={(next) => {
          if (next === allowText) {
            onChange({ text: draft });
          } else {
            onChange({ optionId: next });
          }
        }}
        aria-label="Your answer"
      >
        {options.map((option) => (
          <ChoiceCard
            key={option.id}
            value={option.id}
            title={option.label}
            sub={option.explanation}
            num={option.number}
          />
        ))}
      </ChoiceGroup>
      {allowText !== undefined && radioValue === allowText && (
        <Input
          className="mt-2.5"
          aria-label="Your answer in your own words"
          placeholder="For example: the digits are the store number"
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            onChange({ text: event.target.value });
          }}
        />
      )}
    </div>
  );
}

export function initialSelection(
  options: QuestionOption[],
  defaultOption: string,
): OptionSelection | null {
  if (options.some((option) => option.id === defaultOption)) return { optionId: defaultOption };
  return null;
}
