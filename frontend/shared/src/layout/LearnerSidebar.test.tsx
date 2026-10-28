import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { LearnerSidebar } from "./LearnerSidebar";

afterEach(cleanup);

describe("LearnerSidebar", () => {
  test("shows the 4 pages and Open Charie", () => {
    render(
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
    expect(screen.getByRole("link", { name: "Sources 3 new" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Learning Learning now" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Knowledge 4 to review" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Open Charie" }).getAttribute("href"),
    ).toBe("http://chat.example");
    expect(screen.getByText("Sourabh")).toBeTruthy();
  });

  test("shows the new, live and review badges only when given", () => {
    const { rerender } = render(<LearnerSidebar active="sources" charieUrl="http://chat.example" />);
    expect(screen.queryByText("new")).toBeNull();
    expect(screen.queryByText("Learning now")).toBeNull();
    expect(screen.queryByText("to review")).toBeNull();
    expect(screen.getByRole("link", { name: "Open Charie" })).toBeTruthy();
    rerender(
      <LearnerSidebar
        active="sources"
        newSources={3}
        learningLive
        reviewCount={4}
        charieUrl="http://chat.example"
      />,
    );
    expect(screen.getByText("3 new")).toBeTruthy();
    expect(screen.getByText("Learning now")).toBeTruthy();
    expect(screen.getByText("to review")).toBeTruthy();
  });

  test("hides Open Charie until the URL is loaded", () => {
    render(<LearnerSidebar active="sources" />);
    expect(screen.queryByRole("link", { name: "Open Charie" })).toBeNull();
  });
});
