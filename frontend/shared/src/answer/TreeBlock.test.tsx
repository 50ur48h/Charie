import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { TreeBlock } from "./TreeBlock";
import type { TreeBlock as TreeBlockType } from "../api/chat-types";

afterEach(() => {
  cleanup();
});

function block(nodes: TreeBlockType["nodes"]): TreeBlockType {
  return { type: "tree", title: "Where the drop came from", nodes };
}

describe("TreeBlock", () => {
  test("valid trees render", () => {
    render(
      <TreeBlock
        block={block([
          { id: "a", parent: null, label: "Net sales down $21.4K", tone: "bad" },
          { id: "b", parent: "a", label: "Delivery down $17.2K", tone: "bad" },
        ])}
      />,
    );
    expect(
      screen.getByRole("region", { name: "Where the drop came from" }),
    ).toBeTruthy();
  });

  test("a reachable id loop shows unavailable instead of hanging", () => {
    render(
      <TreeBlock
        block={block([
          { id: "a", parent: null, label: "Root" },
          { id: "q", parent: "a", label: "Mid" },
          { id: "n1", parent: "q", label: "Into the loop" },
          { id: "q", parent: "n1", label: "Loops back", tone: "bad" },
        ])}
      />,
    );
    // The duplicated "q" links the root's chain back into itself: without
    // the guard the kit builder recurses forever.
    expect(screen.getByText("Tree unavailable.")).toBeTruthy();
  });

  test("two roots and orphan cycles stay unavailable, missing parents render", () => {
    const { unmount } = render(
      <TreeBlock
        block={block([
          { id: "a", parent: null, label: "One" },
          { id: "b", parent: null, label: "Two" },
        ])}
      />,
    );
    expect(screen.getByText("Tree unavailable.")).toBeTruthy();
    unmount();
    cleanup();
    render(
      <TreeBlock
        block={block([
          { id: "a", parent: null, label: "Root" },
          { id: "b", parent: "ghost", label: "Orphan" },
        ])}
      />,
    );
    expect(
      screen.getByRole("region", { name: "Where the drop came from" }),
    ).toBeTruthy();
  });
});
