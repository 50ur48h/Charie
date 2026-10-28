import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Database } from "lucide-react";
import { Pill } from "./Pill";

afterEach(cleanup);

describe("Pill", () => {
  test("uses the colors of its tone", () => {
    render(
      <Pill tone="accent" icon={Database}>
        Version 14 · 26 Oct
      </Pill>,
    );
    const pill = screen.getByText("Version 14 · 26 Oct");
    expect(pill.className).toContain("bg-accent-soft");
    expect(pill.className).toContain("text-accent-ink");
  });
});
