import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { MemorySection } from "./MemorySection";

afterEach(cleanup);

const MEMORIES = [
  {
    id: 1,
    text: "For me, sales means without delivery fees.",
    source: 'From the chat "Weekend vs weekday sales" · 12 Oct',
    saved_at: "2025-10-12T00:00:00",
  },
  {
    id: 2,
    text: "I mostly care about the Austin restaurants.",
    source: "From a deleted chat · 20 Oct",
    saved_at: "2025-10-20T00:00:00",
  },
];

function section(props?: Partial<React.ComponentProps<typeof MemorySection>>) {
  return (
    <MemorySection
      memories={MEMORIES}
      isError={false}
      onRetry={() => {}}
      memoryOn={true}
      onForget={() => {}}
      onForgetAll={() => {}}
      forgetting={false}
      forgettingAll={false}
      {...props}
    />
  );
}

describe("MemorySection", () => {
  test("shows the source chat or a deleted chat", () => {
    render(section());
    expect(
      screen.getByText('From the chat "Weekend vs weekday sales" · 12 Oct'),
    ).toBeTruthy();
    expect(screen.getByText("From a deleted chat · 20 Oct")).toBeTruthy();
  });

  test("shows the empty text", () => {
    render(section({ memories: [] }));
    expect(
      screen.getByText(
        'Nothing remembered yet. Tell Charie a preference in any chat, like what "sales" means to you, and it shows up here.',
        { exact: false },
      ),
    ).toBeTruthy();
  });

  test("shows the memory-off note above the list", () => {
    render(section({ memoryOn: false }));
    expect(
      screen.getByText("Memory is off. Charie won't save new preferences or use these until you turn it back on.", {
        exact: false,
      }),
    ).toBeTruthy();
    expect(screen.getByText("For me, sales means without delivery fees.")).toBeTruthy();
  });

  test("forgetting asks which memory to forget", () => {
    const onForget = vi.fn();
    render(section({ onForget }));
    fireEvent.click(screen.getByRole("button", { name: "Forget: I mostly care about the Austin restaurants." }));
    expect(onForget).toHaveBeenCalledWith(2);
  });
});
