import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { MessageStatus } from "./MessageStatus";

describe("MessageStatus", () => {
  test("shows the stopped message", () => {
    render(<MessageStatus status="stopped" />);
    expect(
      screen.getByText("I stopped before finishing. Ask again to get an answer."),
    ).toBeTruthy();
  });

  test("shows the failed message", () => {
    render(<MessageStatus status="failed" />);
    expect(
      screen.getByText("Something went wrong while answering. Please ask again."),
    ).toBeTruthy();
  });
});
