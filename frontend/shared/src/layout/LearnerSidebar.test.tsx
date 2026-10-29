import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, test } from "vitest";
import { LearnerSidebar } from "./LearnerSidebar";

afterEach(cleanup);
function renderSidebar(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}


describe("LearnerSidebar", () => {
  test("shows the 4 pages and Open Charie", () => {
    renderSidebar(
      <LearnerSidebar
        active="sources"
        newSources={3}
        learningLive
        reviewCount={4}
        user={{ name: "Sourabh", detail: "Owner · Bella Forno Group" }}
        charieUrl="http://chat.example"
      />,
    );
    expect(screen.getByRole("link", { name: "Charie Learner" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Setup guide" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Sources 3 new documents" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Learning Learning now" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Knowledge 4 entries need review" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Open Charie" }).getAttribute("href"),
    ).toBe("http://chat.example");
    expect(screen.getByText("Sourabh")).toBeTruthy();
  });

  test("shows the new, live and review badges only when given", () => {
    const { rerender } = renderSidebar(<LearnerSidebar active="sources" charieUrl="http://chat.example" />);
    expect(screen.queryByText("new")).toBeNull();
    expect(screen.queryByText("Learning now")).toBeNull();
    expect(screen.queryByText("to review")).toBeNull();
    expect(screen.getByRole("link", { name: "Open Charie" })).toBeTruthy();
    rerender(
      <MemoryRouter>
        <LearnerSidebar
          active="sources"
          newSources={3}
          learningLive
          reviewCount={4}
          charieUrl="http://chat.example"
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("3 new")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Learning now" })).toBeTruthy();
    expect(screen.getByText("entries need review")).toBeTruthy();
  });

  test("hides Open Charie until the URL is loaded", () => {
    renderSidebar(<LearnerSidebar active="sources" />);
    expect(screen.queryByRole("link", { name: "Open Charie" })).toBeNull();
  });
});
