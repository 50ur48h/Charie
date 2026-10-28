import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Page, PageHeader } from "./PageHeader";

afterEach(cleanup);

describe("PageHeader", () => {
  test("shows the title as the h1, with the lead and actions", () => {
    render(
      <Page>
        <PageHeader title="Usage" lead="What it costs." actions={<button type="button">Limits</button>} />
      </Page>,
    );
    const heading = screen.getByRole("heading", { level: 1, name: "Usage" });
    expect(heading).toBeTruthy();
    expect(screen.getByText("What it costs.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Limits" })).toBeTruthy();
  });
});
