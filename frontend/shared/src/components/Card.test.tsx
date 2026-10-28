import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Card, CardHeader } from "./Card";

afterEach(cleanup);

describe("Card", () => {
  test("CardHeader shows the title and subtitle", () => {
    render(
      <Card padded>
        <CardHeader title="Cost per day" sub="October, in US dollars" />
      </Card>,
    );
    expect(screen.getByRole("heading", { name: "Cost per day" })).toBeTruthy();
    expect(screen.getByText("October, in US dollars")).toBeTruthy();
  });
});
