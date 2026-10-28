import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Markup } from "./markup";

afterEach(() => {
  cleanup();
});

describe("Markup", () => {
  test("allowed_markup renders bold, good, bad and mark spans", () => {
    render(
      <Markup
        text={"Net sales were <good>up 6.2%</good> at **$1.42M**, <bad>downtown fell</bad> and <mark>Oct is partial</mark>."}
      />,
    );
    expect(screen.getByText("up 6.2%").tagName).toBe("SPAN");
    expect(screen.getByText("up 6.2%").className).toContain("text-good-ink");
    expect(screen.getByText("downtown fell").className).toContain("text-bad-ink");
    expect(screen.getByText("Oct is partial").className).toContain("text-accent-ink");
    expect(screen.getByText("$1.42M").tagName).toBe("STRONG");
  });

  test("escapes_html so answer data cannot inject markup", () => {
    render(
      <Markup
        text={'Click <script>alert("x")</script> or <img src="x" onerror="alert(1)"> or <b>bold?</b>'}
      />,
    );
    expect(document.querySelector("script")).toBeNull();
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
    expect(
      screen.getByText('Click <script>alert("x")</script> or', { exact: false }),
    ).toBeTruthy();
  });

  test("long_repeated_unclosed_tags stay literal and fast", () => {
    // 400KB of unclosed openers with content between them: the old
    // backtracking scan needed ~2.2s for the split alone (quadratic). The
    // single-pass scanner stays linear, so this budget has wide margin
    // only when parsing is linear. (Bare ** runs pair up and are not
    // unclosed input, so they are not used here.)
    const text = "<good>x ".repeat(50000);
    const started = performance.now();
    render(<Markup text={text} />);
    expect(performance.now() - started).toBeLessThan(2000);
    expect(document.body.textContent).toBe(text);
    expect(document.querySelectorAll("span, strong").length).toBe(0);
  });

  test("incomplete_tags and unknown spans stay literal", () => {
    render(
      <Markup
        text={"Stray <good>open and <neutral>accent?</neutral> plus <foo>bar</foo> and **open"}
      />,
    );
    // <neutral> is not in the allowed set, so it stays plain text.
    expect(screen.getByText("Stray <good>open and", { exact: false })).toBeTruthy();
    expect(screen.getByText("<neutral>accent?</neutral> plus", { exact: false })).toBeTruthy();
    expect(screen.getByText("<foo>bar</foo> and **open", { exact: false })).toBeTruthy();
    expect(document.querySelector("foo")).toBeNull();
  });
});
