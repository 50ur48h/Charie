import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Spinner } from "./Spinner";

afterEach(cleanup);

describe("Spinner", () => {
  test("has a status role only when it has a label", () => {
    render(<Spinner label="Loading" />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeTruthy();
    cleanup();
    const { container } = render(<Spinner />);
    expect(screen.queryByRole("status")).toBeNull();
    expect(container.firstElementChild?.getAttribute("aria-hidden")).toBe("true");
  });
});
