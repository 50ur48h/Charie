import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { SetupSteps } from "./SetupSteps";

afterEach(() => {
  cleanup();
});

describe("SetupSteps", () => {
  test("shows step 2 of 5 with the first done", () => {
    const onOpen = vi.fn();
    render(<SetupSteps current={2} open={2} done={false} onOpen={onOpen} />);
    expect(screen.getByText("Step 2 of 5")).toBeTruthy();
    // Step 1 is done; step 2 is open.
    const first = screen.getByRole("button", { name: /Connect your database/ });
    expect(first.querySelector("svg")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Add documents and notes/ }).getAttribute("aria-current"),
    ).toBe("step");
    fireEvent.click(screen.getByRole("button", { name: /Let Charie learn/ }));
    expect(onOpen).toHaveBeenCalledWith(3);
  });
});
