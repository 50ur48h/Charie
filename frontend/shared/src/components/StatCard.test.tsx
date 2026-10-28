import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { StatCard } from "./StatCard";

afterEach(cleanup);

describe("StatCard", () => {
  test("shows the label, value and foot", () => {
    render(<StatCard label="Spent this month" value="$41.20" foot="1–27 Oct" />);
    expect(screen.getByText("Spent this month")).toBeTruthy();
    expect(screen.getByText("$41.20")).toBeTruthy();
    expect(screen.getByText("1–27 Oct")).toBeTruthy();
  });
});
