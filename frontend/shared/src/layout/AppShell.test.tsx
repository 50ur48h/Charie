import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { AppShell } from "./AppShell";
import { useSidebarHidden } from "./useSidebarHidden";

afterEach(cleanup);

function HiddenProbe() {
  const [hidden, setHidden] = useSidebarHidden();
  return (
    <button type="button" onClick={() => setHidden(!hidden)}>
      {hidden ? "hidden" : "shown"}
    </button>
  );
}

describe("AppShell", () => {
  test("hides and shows the sidebar", async () => {
    const user = userEvent.setup();
    const onShowSidebar = vi.fn();
    const { rerender } = render(
      <AppShell
        app="chat"
        sidebar={() => <nav aria-label="Column" />}
        sidebarHidden={false}
        onShowSidebar={onShowSidebar}
      >
        <p>Page body</p>
      </AppShell>,
    );
    expect(screen.getByRole("navigation", { name: "Column" })).toBeTruthy();
    expect(screen.getByText("Page body")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Skip to content" }).getAttribute("href"),
    ).toBe("#main");
    rerender(
      <AppShell
        app="chat"
        sidebar={() => <nav aria-label="Column" />}
        sidebarHidden
        onShowSidebar={onShowSidebar}
      >
        <p>Page body</p>
      </AppShell>,
    );
    expect(screen.queryByRole("navigation", { name: "Column" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Show sidebar" }));
    expect(onShowSidebar).toHaveBeenCalledTimes(1);
  });

  test("remembers a hidden sidebar", async () => {
    const user = userEvent.setup();
    localStorage.clear();
    const { unmount } = render(<HiddenProbe />);
    expect(screen.getByRole("button", { name: "shown" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "shown" }));
    expect(localStorage.getItem("charie-sidebar-hidden")).toBe("1");
    unmount();
    render(<HiddenProbe />);
    expect(screen.getByRole("button", { name: "hidden" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "hidden" }));
    expect(localStorage.getItem("charie-sidebar-hidden")).toBe("0");
  });
});
