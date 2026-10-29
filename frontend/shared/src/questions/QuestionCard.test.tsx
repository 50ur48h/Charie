import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { QuestionCard } from "./QuestionCard";
import { seedQuestions } from "../mocks/sampleQuestions";
import type { OptionSelection } from "./QuestionOptions";

afterEach(cleanup);

const waiting = seedQuestions[0];

function checked(name: RegExp): boolean {
  return screen.getByRole("radio", { name }).getAttribute("aria-checked") === "true";
}

describe("QuestionCard", () => {
  test("default_not_auto_saved: mounting selects the default but saves nothing", async () => {
    const onSave = vi.fn();
    render(
      <QuestionCard question={waiting} onSave={onSave} onSkip={vi.fn()} />,
    );
    // The default option is selected (design preselects it)…
    expect(checked(/Including delivery fees/)).toBe(true);
    // …but mounting alone never calls onSave.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(onSave).not.toHaveBeenCalled();
  });

  test("evidence: summary, docs and numbers render from fixtures", () => {
    render(<QuestionCard question={waiting} onSave={vi.fn()} onSkip={vi.fn()} />);
    const card = screen.getByRole("region", { name: waiting.title });
    expect(card.textContent).toContain("Two documents disagree");
    expect(card.textContent).toContain('Finance wiki - "Net sales"');
    expect(card.textContent).toContain("$1.42M");
    // The second fixture's table renders rows from fixture values.
    cleanup();
    render(
      <QuestionCard question={seedQuestions[1]} onSave={vi.fn()} onSkip={vi.fn()} />,
    );
    expect(screen.getByText("9001 - Test Kitchen A")).not.toBeNull();
  });

  test("save_and_failure: selection saves explicitly; failure keeps it", async () => {
    const user = userEvent.setup();
    const calls: OptionSelection[] = [];
    // A save that always fails: the card must keep the selection.
    render(
      <QuestionCard
        question={waiting}
        onSave={(selection) => {
          calls.push(selection);
        }}
        onSkip={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("radio", { name: /Without delivery fees/ }));
    await user.click(screen.getByRole("button", { name: "Save answer" }));
    expect(calls).toEqual([{ optionId: "without-fees" }]);
    // The failed save kept the new selection.
    expect(checked(/Without delivery fees/)).toBe(true);
  });

  test("save_error: the parent message shows without clearing the choice", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <QuestionCard
        question={waiting}
        saveError="Couldn't save that answer. Try again."
        onSave={onSave}
        onSkip={vi.fn()}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Couldn't save that answer. Try again.");
    expect(checked(/Including delivery fees/)).toBe(true);
    await user.click(screen.getByRole("button", { name: "Save answer" }));
    expect(onSave).toHaveBeenCalledWith({ optionId: "with-fees" });
    expect(checked(/Including delivery fees/)).toBe(true);
  });

  test("change_init_option: an answered card starts from the saved non-default choice", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const answered = {
      ...waiting,
      status: "answered" as const,
      answer: { optionId: "without-fees" },
    };
    render(<QuestionCard question={answered} onSave={onSave} onSkip={vi.fn()} />);
    // The saved non-default choice is selected; the default is not.
    expect(checked(/Without delivery fees/)).toBe(true);
    expect(checked(/Including delivery fees/)).toBe(false);
    expect(onSave).not.toHaveBeenCalled();
    // Saving untouched preserves the saved choice.
    await user.click(screen.getByRole("button", { name: "Save answer" }));
    expect(onSave).toHaveBeenCalledWith({ optionId: "without-fees" });
  });

  test("change_init_text: the text box shows the saved free-text answer", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const answered = {
      ...seedQuestions[2],
      status: "answered" as const,
      answer: { text: "the digits are the store number" },
    };
    render(<QuestionCard question={answered} onSave={onSave} onSkip={vi.fn()} />);
    expect(checked(/Something else/)).toBe(true);
    expect(
      (screen.getByLabelText("Your answer in your own words") as HTMLInputElement).value,
    ).toBe("the digits are the store number");
    expect(onSave).not.toHaveBeenCalled();
    // Saving untouched preserves the free-text answer.
    await user.click(screen.getByRole("button", { name: "Save answer" }));
    expect(onSave).toHaveBeenCalledWith({ text: "the digits are the store number" });
  });

  test("something_else: free text saves trimmed, blank text is refused", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<QuestionCard question={seedQuestions[2]} onSave={onSave} onSkip={vi.fn()} />);
    await user.click(screen.getByRole("radio", { name: /Something else/ }));
    expect(checked(/Something else/)).toBe(true);
    const box = screen.getByLabelText("Your answer in your own words");
    await user.click(screen.getByRole("button", { name: "Save answer" }));
    // Blank text is refused without calling onSave.
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain("Pick an option");
    await user.type(box, "  the digits are the store number  ");
    await user.click(screen.getByRole("button", { name: "Save answer" }));
    expect(onSave).toHaveBeenCalledWith({ text: "the digits are the store number" });
  });
});
