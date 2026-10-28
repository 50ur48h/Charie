import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Brand, LogoMark } from "./Logo";

afterEach(cleanup);

describe("Logo", () => {
  test("LogoMark renders the mark at the given size", () => {
    const { container } = render(<LogoMark size={52} />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe("52");
    expect(svg?.getAttribute("height")).toBe("52");
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
  });

  test("Brand shows the Learner tag only in the learner", () => {
    const { rerender } = render(<Brand app="chat" href="/" />);
    expect(screen.getByRole("link", { name: "Charie" }).getAttribute("href")).toBe("/");
    expect(screen.queryByText("Learner")).toBeNull();
    rerender(<Brand app="learner" href="/setup" />);
    expect(screen.getByRole("link", { name: "Charie Learner" }).getAttribute("href")).toBe(
      "/setup",
    );
    expect(screen.getByText("Learner")).toBeTruthy();
  });
});
