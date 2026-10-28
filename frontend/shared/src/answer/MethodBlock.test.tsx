import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { MethodBlock } from "./MethodBlock";
import type { MethodBlock as MethodBlockType } from "../api/chat-types";

afterEach(() => {
  cleanup();
});

const BLOCK: MethodBlockType = {
  type: "method",
  definitions: ["Net sales leave out refunds."],
  steps: ["Added up sales by restaurant for October and September."],
  queries: [{ purpose: "Monthly sales by restaurant", sql: "SELECT <b>bold?</b>" }],
  sources: [{ document: "Incident log.docx", quote: "Ovens <broken>", location: "page 2" }],
};

describe("MethodBlock", () => {
  test("query_and_source_evidence", () => {
    render(<MethodBlock block={BLOCK} />);
    const onScreen = () => within(document.querySelector(".method-screen") as HTMLElement);
    expect(screen.getByText("How I worked this out")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Data used/ }));
    // SQL renders as text, never HTML: no bold element is created.
    expect(onScreen().getByText("Monthly sales by restaurant")).toBeTruthy();
    expect(document.querySelector("b")).toBeNull();
    expect(onScreen().getByText("SELECT <b>bold?</b>")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Sources/ }));
    expect(onScreen().getByText("Ovens <broken>")).toBeTruthy();
    expect(document.querySelector("blockquote")).toBeTruthy();
  });

  test("sections expand with a keyboard-operated button", () => {
    render(<MethodBlock block={BLOCK} />);
    const onScreen = () => within(document.querySelector(".method-screen") as HTMLElement);
    const toggle = screen.getByRole("button", { name: /Steps/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(onScreen().queryByText(BLOCK.steps[0])).toBeNull();
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(onScreen().getByText(BLOCK.steps[0])).toBeTruthy();
  });
});
