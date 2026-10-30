import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { filterEntries, groupCounts } from "./groups";
import { KnowledgeList } from "./KnowledgeList";
import { listMockKnowledge } from "../mocks/sampleKnowledge";
import type { KnowledgeGroup } from "./groups";

afterEach(cleanup);

const FULL_COUNTS = {
  metric: 4,
  default: 3,
  table: 1,
  column: 1,
  rule: 2,
  code: 1,
  event: 1,
  data_problem: 1,
};

function renderList(group: KnowledgeGroup = "all", selectedKey: string | null = null) {
  const onSelect = vi.fn();
  const onGroupChange = vi.fn();
  render(
    <KnowledgeList
      entries={filterEntries(listMockKnowledge({}), group, "")}
      counts={groupCounts(FULL_COUNTS)}
      needsReview={4}
      group={group}
      query=""
      selectedKey={selectedKey}
      onGroupChange={onGroupChange}
      onQueryChange={vi.fn()}
      onSelect={onSelect}
    />,
  );
  return { onSelect, onGroupChange };
}

describe("KnowledgeList", () => {
  test("groups kinds into the 7 buttons", async () => {
    const user = userEvent.setup();
    const { onGroupChange } = renderList();
    for (const label of [
      "Business numbers",
      "Words & meanings",
      "Tables & columns",
      "Rules",
      "Codes",
      "Events",
      "Data problems",
    ]) {
      expect(screen.getByRole("button", { name: new RegExp(label) })).not.toBeNull();
    }
    expect(screen.getByRole("button", { name: /Business numbers 4/ })).not.toBeNull();
    await user.click(screen.getByRole("button", { name: /Words & meanings/ }));
    expect(onGroupChange).toHaveBeenCalledWith("words");
    // Parent filters the entries; the list shows the filtered rows.
    cleanup();
    renderList("words");
    expect(screen.queryByRole("option", { name: /^Net sales/ })).toBeNull();
    expect(screen.getByRole("option", { name: /^"Lunch"/ })).not.toBeNull();
  });

  test("search filters the shown entries", async () => {
    const user = userEvent.setup();
    const onQueryChange = vi.fn();
    render(
      <KnowledgeList
        entries={listMockKnowledge({})}
        counts={groupCounts(FULL_COUNTS)}
        needsReview={4}
        group="all"
        query=""
        selectedKey={null}
        onGroupChange={vi.fn()}
        onQueryChange={onQueryChange}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole("option", { name: /^Net sales / })).not.toBeNull();
    await user.type(screen.getByLabelText("Search everything Charie has learned"), "lunch");
    expect(onQueryChange).toHaveBeenCalled();
  });

  test("empty: no matches explains itself", () => {
    render(
      <KnowledgeList
        entries={[]}
        counts={groupCounts({})}
        needsReview={0}
        group="words"
        query="zzz-no-such-thing"
        selectedKey={null}
        onGroupChange={vi.fn()}
        onQueryChange={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("Nothing matches. Try another word.")).not.toBeNull();
    expect(screen.queryByRole("option")).toBeNull();
  });

  test("selection by stable key", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderList();
    await user.click(screen.getByRole("option", { name: /Average order/ }));
    expect(onSelect).toHaveBeenCalledWith("metric.avg_order");
  });

  test("editable: Needs review shows guessed and conflicting only", async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeList
        entries={listMockKnowledge({})}
        counts={groupCounts(FULL_COUNTS)}
        needsReview={4}
        group="all"
        query=""
        selectedKey={null}
        editable
        onGroupChange={vi.fn()}
        onQueryChange={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /Needs review/ })).not.toBeNull();
    await user.click(screen.getByRole("button", { name: /Needs review 4/ }));
    const shown = screen.getAllByRole("option");
    expect(shown).toHaveLength(4);
    expect(screen.getByRole("option", { name: /Labor cost %/ })).not.toBeNull();
    expect(screen.queryByRole("option", { name: /^Net sales/ })).toBeNull();
  });

  test("editable: an empty Needs review explains itself", async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeList
        entries={filterEntries(listMockKnowledge({}), "tables", "")}
        counts={groupCounts(FULL_COUNTS)}
        needsReview={4}
        group="tables"
        query=""
        selectedKey={null}
        editable
        onGroupChange={vi.fn()}
        onQueryChange={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Needs review/ }));
    expect(screen.getByText("Nothing needs review right now.")).not.toBeNull();
    expect(screen.queryByRole("option")).toBeNull();
  });

  test("read_only: no review tabs without editable", () => {
    renderList();
    expect(screen.queryByRole("button", { name: /Needs review/ })).toBeNull();
  });
});
