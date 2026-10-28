import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./Tabs";

afterEach(cleanup);

function TwoTabs() {
  return (
    <Tabs defaultValue="waiting">
      <TabsList aria-label="Questions">
        <TabsTrigger value="waiting" count={3}>
          Waiting
        </TabsTrigger>
        <TabsTrigger value="answered" count={12}>
          Answered
        </TabsTrigger>
      </TabsList>
      <TabsContent value="waiting">Waiting list</TabsContent>
      <TabsContent value="answered">Answered list</TabsContent>
    </Tabs>
  );
}

describe("Tabs", () => {
  test("arrow keys move to the next tab and show its panel", async () => {
    const user = userEvent.setup();
    render(<TwoTabs />);
    await user.click(screen.getByRole("tab", { name: /Waiting/ }));
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /Answered/ }).getAttribute("data-state")).toBe("active");
    expect(screen.getByText("Answered list")).toBeTruthy();
  });

  test("shows the count", () => {
    render(<TwoTabs />);
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
  });
});
