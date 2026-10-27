import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("shows the app name", () => {
    render(<App />);
    expect(screen.getByRole("heading").textContent).toBe("Charie Learner");
  });
});
