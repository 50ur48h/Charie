import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import type { KnowledgeVersion } from "@charie/shared";
import { DraftBanner } from "./DraftBanner";

afterEach(cleanup);

function draftVersion(): KnowledgeVersion {
  return {
    id: 15,
    number: 15,
    status: "draft",
    changes: 6,
    summary: {
      added: 3,
      changed: 2,
      removed: 1,
      note: "3 new facts from new documents \u00b7 2 updated meanings \u00b7 1 removed",
    },
  };
}

function renderBanner(version: KnowledgeVersion | null, liveNumber: number | null) {
  const onReview = vi.fn();
  const onPublish = vi.fn();
  render(
    <DraftBanner version={version} liveNumber={liveNumber} onReview={onReview} onPublish={onPublish} />,
  );
  return { onReview, onPublish };
}

describe("DraftBanner", () => {
  test("shows draft 15 with 6 changes", () => {
    renderBanner(draftVersion(), 14);
    expect(screen.getByText("Draft version 15 has 6 changes")).not.toBeNull();
    expect(
      screen.getByText(/3 new facts from new documents.*Version 14 stays live until you publish\./),
    ).not.toBeNull();
    expect(screen.getByRole("button", { name: "Review changes" })).not.toBeNull();
    expect(screen.getByRole("button", { name: "Publish version 15" })).not.toBeNull();
  });

  test("hides with no draft", () => {
    const { container } = render(
      <DraftBanner version={null} liveNumber={14} onReview={vi.fn()} onPublish={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  test("hides when the version is published", () => {
    const { container } = render(
      <DraftBanner
        version={{ ...draftVersion(), status: "published" }}
        liveNumber={15}
        onReview={vi.fn()}
        onPublish={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });
});
