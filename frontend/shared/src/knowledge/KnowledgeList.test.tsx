import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { KnowledgeList } from "./KnowledgeList";
import { listMockKnowledge } from "../mocks/sampleKnowledge";

afterEach(cleanup);

function renderList(selectedKey: string | null = null) {
  const onSelect = vi.fn();
  render(
    <KnowledgeList
      entries={listMockKnowledge({})}
      counts={{ all: 14, number: 4 }}
      kind="all"
      query=""
      selectedKey={selectedKey}
      onKindChange={vi.fn()}
      onQueryChange={vi.fn()}
      onSelect={onSelect}
    />,
  );
  return onSelect;
}

describe("KnowledgeList", () => {
  test("search_and_kind: filters combine", async () => {
    const user = userEvent.setup();
    const onKindChange = vi.fn();
    const onQueryChange = vi.fn();
    const { rerender } = render(
      <KnowledgeList
        entries={listMockKnowledge({})}
        counts={{ all: 14 }}
        kind="all"
        query=""
        selectedKey={null}
        onKindChange={onKindChange}
        onQueryChange={onQueryChange}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole("option", { name: /^Net sales / })).not.toBeNull();
    await user.click(screen.getByRole("button", { name: /Business numbers/ }));
    expect(onKindChange).toHaveBeenCalledWith("number");
    // Parent filters the entries; the list shows the filtered rows.
    rerender(
      <KnowledgeList
        entries={listMockKnowledge({ kind: "number" })}
        counts={{ all: 14 }}
        kind="number"
        query=""
        selectedKey={null}
        onKindChange={onKindChange}
        onQueryChange={onQueryChange}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByRole("option", { name: /"Lunch"/ })).toBeNull();
    expect(screen.getByRole("option", { name: /Food cost %/ })).not.toBeNull();
    await user.type(screen.getByLabelText("Search everything Charie has learned"), "lunch");
    expect(onQueryChange).toHaveBeenCalled();
  });

  test("empty: no matches explains itself", () => {
    render(
      <KnowledgeList
        entries={[]}
        counts={{ all: 0 }}
        kind="word"
        query="zzz-no-such-thing"
        selectedKey={null}
        onKindChange={vi.fn()}
        onQueryChange={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("Nothing matches. Try another word.")).not.toBeNull();
    expect(screen.queryByRole("option")).toBeNull();
  });

  test("selection by stable key", async () => {
    const user = userEvent.setup();
    const onSelect = renderList();
    await user.click(screen.getByRole("option", { name: /Average order/ }));
    expect(onSelect).toHaveBeenCalledWith("metric.avg_order");
  });
});
