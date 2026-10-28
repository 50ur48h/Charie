import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { SquarePen } from "lucide-react";
import { Button, IconButton } from "./Button";

afterEach(cleanup);

describe("Button", () => {
  test("is type button by default", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" }).getAttribute("type")).toBe("button");
  });

  test("asChild renders a link that looks like a button", () => {
    render(
      <Button asChild variant="soft">
        <a href="/usage">See usage</a>
      </Button>,
    );
    const link = screen.getByRole("link", { name: "See usage" });
    expect(link.getAttribute("href")).toBe("/usage");
    expect(link.className).toContain("inline-flex");
    expect(link.className).toContain("bg-accent-soft");
  });

  test("IconButton uses its label as its name", () => {
    render(
      <IconButton label="Hide sidebar">
        <SquarePen />
      </IconButton>,
    );
    const button = screen.getByRole("button", { name: "Hide sidebar" });
    expect(button.getAttribute("title")).toBe("Hide sidebar");
  });
});
