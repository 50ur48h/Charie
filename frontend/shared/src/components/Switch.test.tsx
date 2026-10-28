import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";
import { Switch } from "./Switch";

afterEach(cleanup);

describe("Switch", () => {
  test("toggles with a click and with the Space key", async () => {
    const user = userEvent.setup();
    render(<Switch aria-label="Remember things I tell Charie" />);
    const toggle = screen.getByRole("switch", { name: "Remember things I tell Charie" });
    expect(toggle.getAttribute("data-state")).toBe("unchecked");
    await user.click(toggle);
    expect(toggle.getAttribute("data-state")).toBe("checked");
    toggle.focus();
    await user.keyboard(" ");
    expect(toggle.getAttribute("data-state")).toBe("unchecked");
  });
});
