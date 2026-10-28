import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { SpendingBanner } from "./SpendingBanner";
import { SpendingLimitsDialog } from "./SpendingLimitsDialog";
import { mockSpending, mockUsage } from "../mocks/sampleUsage";

afterEach(cleanup);

describe("SpendingBanner", () => {
  test("zero_spend: no banner when everything is fine", () => {
    const { container } = render(
      <SpendingBanner spending={mockSpending(0)} onManage={vi.fn()} />,
    );
    expect(container.textContent).toBe("");
  });

  test("warning shows the percent and a limits action", async () => {
    const user = userEvent.setup();
    const onManage = vi.fn();
    render(<SpendingBanner spending={{ ...mockSpending(41.2), state: "warn", percent_used: 85 }} onManage={onManage} />);
    expect(screen.getByText(/85% of your credit/)).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Spending limits" }));
    expect(onManage).toHaveBeenCalled();
  });

  test("paused blocks with a raise action", () => {
    render(<SpendingBanner spending={mockSpending(150)} onManage={vi.fn()} />);
    expect(screen.getByRole("alert").textContent).toContain("Questions are paused.");
    expect(screen.getByRole("button", { name: "Raise limit" })).not.toBeNull();
  });
});

describe("SpendingLimitsDialog", () => {
  function dialog(onSave: (patch: unknown) => void) {
    const client = new QueryClient();
    const wrap = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    return render(
      <SpendingLimitsDialog limitUsd={150} warnPercent={80} onSave={onSave as never} onClose={vi.fn()} />,
      { wrapper: wrap },
    );
  }

  test("limit_validation: nonsense stays local with a plain message", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    dialog(onSave);
    await user.clear(screen.getByLabelText("Monthly credit (USD)"));
    await user.type(screen.getByLabelText("Monthly credit (USD)"), "-5");
    await user.click(screen.getByRole("button", { name: "Save limits" }));
    const alerts = () => screen.getAllByRole("alert").map((a) => a.textContent).join(" ");
    expect(alerts()).toContain("more than $0");
    expect(onSave).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText("Monthly credit (USD)"));
    await user.type(screen.getByLabelText("Monthly credit (USD)"), "200");
    await user.clear(screen.getByLabelText("Warn me at (percent)"));
    await user.type(screen.getByLabelText("Warn me at (percent)"), "150");
    await user.click(screen.getByRole("button", { name: "Save limits" }));
    expect(alerts()).toContain("between 1 and 99");
    expect(onSave).not.toHaveBeenCalled();
  });
});

describe("mockUsage", () => {
  test("month_change: populated demo month vs zero-spend month", () => {
    const demo = mockUsage("2025-10");
    expect(demo.spent_usd).toBe(41.2);
    expect(demo.per_day).toHaveLength(27);
    expect(demo.per_group).toHaveLength(6);
    expect(demo.top_questions).toHaveLength(5);
    expect(demo.state).toBe("ok");
    const empty = mockUsage("2025-01");
    expect(empty.spent_usd).toBe(0);
    expect(empty.per_group).toEqual([]);
    expect(empty.top_questions).toEqual([]);
    expect(empty.questions.count).toBe(0);
  });
});
