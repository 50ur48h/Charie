// One quick question with clickable choices (P11.3): the AI's text in
// the answer's serif font, the options as ChoiceCards without numbers
// (two columns, one under 900 px), then the muted hint. Only the
// newest message is clickable; older ones show the picked card.
import { ChoiceCard, ChoiceGroup } from "../components/ChoiceCard";

export interface QuickChoiceOption {
  id: string;
  label: string;
}

export function QuickChoice({
  text,
  options,
  chosenLabel,
  disabled,
  onChoose,
}: {
  text: string;
  options: QuickChoiceOption[];
  chosenLabel: string | null;
  disabled: boolean;
  onChoose: (id: string) => void;
}) {
  const chosen = options.find((option) => option.label === chosenLabel)?.id;
  return (
    <div className="mb-4">
      <p className="m-0 mb-2 font-serif text-[15.5px] leading-relaxed">{text}</p>
      <ChoiceGroup
        aria-label={text}
        value={chosen}
        onValueChange={(id) => {
          if (!disabled && typeof id === "string") onChoose(id);
        }}
        className="grid-cols-2 max-[900px]:grid-cols-1"
      >
        {options.map((option) => (
          <ChoiceCard
            key={option.id}
            value={option.id}
            title={option.label}
            disabled={disabled}
          />
        ))}
      </ChoiceGroup>
      {!disabled && chosen === undefined && (
        <p className="mt-2 text-[13px] text-muted">Pick one, or type your own answer below.</p>
      )}
    </div>
  );
}
