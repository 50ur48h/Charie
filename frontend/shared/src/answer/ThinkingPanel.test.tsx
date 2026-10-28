import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { failedThinking } from "../mocks/sampleThinking";
import type { ThinkingKind } from "./thinking";
import { ThinkingPanel } from "./ThinkingPanel";

afterEach(cleanup);

const KINDS: ThinkingKind[] = ["step", "found", "query", "document", "decision", "check", "note"];

describe("ThinkingPanel", () => {
  test("renders all seven thinking kinds", () => {
    render(
      <ThinkingPanel
        lines={KINDS.map((kind, index) => ({
          seq: index + 1,
          kind,
          status: "done" as const,
          title: `${kind} line`,
          at: "2025-10-26T12:00:00Z",
        }))}
        summary={null}
        panelId="kinds"
      />,
    );
    // A finished panel starts shut; the rows appear after opening it.
    expect(screen.queryByRole("button", { name: /step line/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Thinking" }));
    for (const kind of KINDS) {
      expect(screen.getByRole("button", { name: new RegExp(`${kind} line`) })).toBeTruthy();
    }
  });

  test("a failed line shows its explanation exactly once", () => {
    render(<ThinkingPanel lines={failedThinking} summary={null} panelId="failed" />);
    expect(
      screen.getAllByText(
        "The sales extract stopped updating on 24 Oct, so these numbers leave out the last two days.",
      ),
    ).toHaveLength(1);
  });

  test("an empty timeline renders nothing", () => {
    const { container } = render(<ThinkingPanel lines={[]} summary={null} panelId="empty" />);
    expect(container.innerHTML).toBe("");
  });
});
