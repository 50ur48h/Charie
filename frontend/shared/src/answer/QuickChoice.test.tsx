import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { QuickChoice } from "./QuickChoice";

afterEach(cleanup);

const OPTIONS = [
  { id: "by_net_sales", label: "By net sales" },
  { id: "by_growth", label: "By growth" },
];

describe("QuickChoice", () => {
  test("shows the question, options and hint", () => {
    render(
      <QuickChoice
        text="How should I rank them?"
        options={OPTIONS}
        chosenLabel={null}
        disabled={false}
        onChoose={() => {}}
      />,
    );
    expect(screen.getByText("How should I rank them?")).toBeTruthy();
    expect(screen.getByRole("radio", { name: "By net sales" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "By growth" })).toBeTruthy();
    expect(screen.getByText("Pick one, or type your own answer below.")).toBeTruthy();
  });

  test("clicking sends the option id", async () => {
    const user = userEvent.setup();
    const onChoose = vi.fn();
    render(
      <QuickChoice
        text="How should I rank them?"
        options={OPTIONS}
        chosenLabel={null}
        disabled={false}
        onChoose={onChoose}
      />,
    );
    await user.click(screen.getByRole("radio", { name: "By growth" }));
    expect(onChoose).toHaveBeenCalledWith("by_growth");
  });

  test("older choices show the picked option and can't be clicked", async () => {
    const user = userEvent.setup();
    const onChoose = vi.fn();
    render(
      <QuickChoice
        text="How should I rank them?"
        options={OPTIONS}
        chosenLabel="By growth"
        disabled={true}
        onChoose={onChoose}
      />,
    );
    expect(screen.getByRole("radio", { name: "By growth" }).getAttribute("data-state")).toBe(
      "checked",
    );
    expect(screen.queryByText("Pick one, or type your own answer below.")).toBeNull();
    await user.click(screen.getByRole("radio", { name: "By net sales" }));
    expect(onChoose).not.toHaveBeenCalled();
  });
});
