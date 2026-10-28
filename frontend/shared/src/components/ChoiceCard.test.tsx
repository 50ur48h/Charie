import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";
import { ChoiceCard, ChoiceGroup } from "./ChoiceCard";

afterEach(cleanup);

describe("ChoiceCard", () => {
  test("picks a choice with a click", async () => {
    const user = userEvent.setup();
    render(
      <ChoiceGroup aria-label='What should "sales" mean by default?' defaultValue="with">
        <ChoiceCard value="with" title="Including delivery fees" sub="Matches the Finance wiki" num="$1.42M" />
        <ChoiceCard value="without" title="Without delivery fees" sub="Matches the Ops handbook" num="$1.31M" />
      </ChoiceGroup>,
    );
    const without = screen.getByRole("radio", { name: /Without delivery fees/ });
    expect(without.getAttribute("data-state")).toBe("unchecked");
    await user.click(without);
    expect(without.getAttribute("data-state")).toBe("checked");
  });

  test("arrow keys move to the next choice", async () => {
    render(
      <ChoiceGroup aria-label="Pick one" defaultValue="a">
        <ChoiceCard value="a" title="Alpha" />
        <ChoiceCard value="b" title="Beta" />
      </ChoiceGroup>,
    );
    // Key down only: browsers release the key after Radix's deferred focus
    // moves and checks the next item; user-event's instant key up clears
    // Radix's arrow flag too early in jsdom.
    const alpha = screen.getByRole("radio", { name: "Alpha" });
    alpha.focus();
    fireEvent.keyDown(alpha, { key: "ArrowDown" });
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "Beta" }).getAttribute("data-state")).toBe("checked"),
    );
  });
});
