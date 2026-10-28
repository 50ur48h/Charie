import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";
import { routes } from "./routes";

afterEach(cleanup);

function renderAt(path: string) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);
}

describe("learner routes", () => {
  test("shows the setup guide at /setup", async () => {
    renderAt("/setup");
    expect(await screen.findByRole("heading", { name: "Set up Charie" })).toBeTruthy();
  });

  test("sends / to /setup", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "Set up Charie" })).toBeTruthy();
  });
});
