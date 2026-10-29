import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { DocumentStatus } from "./DocumentStatus";
import type { LearnerDocument } from "@charie/shared";

function doc(overrides: Partial<LearnerDocument>): LearnerDocument {
  return {
    id: 1,
    file_name: "Finance wiki.pdf",
    file_type: "pdf",
    size_bytes: 1024,
    pages: 24,
    unreadable_pages: 0,
    fact_count: 41,
    status: "learned",
    progress: null,
    error: null,
    uploaded_at: "2026-10-03T10:02:00+05:30",
    learned_at: "2026-10-03T10:20:00+05:30",
    ...overrides,
  };
}

describe("DocumentStatus", () => {
  test("shows each status like the design", () => {
    const { rerender } = render(<DocumentStatus document={doc({ status: "new" })} />);
    expect(screen.getByText("New · not learned yet")).toBeTruthy();

    rerender(<DocumentStatus document={doc({ status: "reading", progress: 64 })} />);
    expect(screen.getByText("Reading")).toBeTruthy();

    rerender(<DocumentStatus document={doc({ status: "learned", fact_count: 41 })} />);
    expect(screen.getByText("Learned · 41 facts")).toBeTruthy();

    rerender(<DocumentStatus document={doc({ status: "learned", fact_count: 1 })} />);
    expect(screen.getByText("Learned · 1 fact")).toBeTruthy();

    rerender(
      <DocumentStatus document={doc({ status: "learned", fact_count: 5, unreadable_pages: 2 })} />,
    );
    expect(screen.getByText("2 pages unreadable")).toBeTruthy();

    rerender(
      <DocumentStatus
        document={doc({ status: "failed", error: "The file is empty.", unreadable_pages: 0 })}
      />,
    );
    expect(screen.getByText("Couldn't read it")).toBeTruthy();
  });
});
