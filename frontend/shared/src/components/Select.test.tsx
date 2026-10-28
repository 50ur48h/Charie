import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Select } from "./Select";

afterEach(cleanup);

const OPTIONS = [
  { value: "short", label: "Short" },
  { value: "normal", label: "Normal" },
  { value: "detailed", label: "Detailed" },
];

describe("Select", () => {
  test("shows the chosen option's label", () => {
    render(<Select options={OPTIONS} value="normal" placeholder="Thinking time" />);
    expect(screen.getByRole("combobox").textContent).toContain("Normal");
  });

  test("picking an option calls onValueChange", () => {
    const onValueChange = vi.fn();
    render(<Select options={OPTIONS} value="normal" onValueChange={onValueChange} placeholder="Thinking time" />);
    const trigger = screen.getByRole("combobox");
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: "Detailed" }));
    expect(onValueChange).toHaveBeenCalledWith("detailed");
  });
});
