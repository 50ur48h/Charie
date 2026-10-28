import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";
import { Button } from "./Button";
import { Toaster, toast } from "./Toast";

afterEach(cleanup);

describe("Toast", () => {
  test("toast shows the message", async () => {
    const user = userEvent.setup();
    render(
      <>
        <Toaster />
        <Button onClick={() => toast("Saved. Charie is re-checking what this affects.")}>
          Show a toast
        </Button>
      </>,
    );
    await user.click(screen.getByRole("button", { name: "Show a toast" }));
    expect(await screen.findByText("Saved. Charie is re-checking what this affects.")).toBeTruthy();
  });
});
