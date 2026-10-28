import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Field, Input } from "./Input";

afterEach(cleanup);

describe("Field", () => {
  test("Field links the label to the input", () => {
    render(
      <Field label="Password" htmlFor="kit-password" hint="Stored safely and never shown again.">
        <Input id="kit-password" type="password" />
      </Field>,
    );
    expect(screen.getByLabelText("Password").getAttribute("id")).toBe("kit-password");
    expect(screen.getByText("Stored safely and never shown again.")).toBeTruthy();
  });

  test("Field shows the error and links it to the input", () => {
    render(
      <Field label="Password" htmlFor="kit-password-bad" error="That password didn't work. Try again.">
        <Input id="kit-password-bad" type="password" aria-invalid="true" />
      </Field>,
    );
    const input = screen.getByLabelText("Password");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const error = screen.getByRole("alert");
    expect(error.getAttribute("id")).toBe(describedBy);
    expect(error.textContent).toContain("That password didn't work. Try again.");
  });
});
