import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Download } from "lucide-react";
import { IconButton } from "./Button";
import { Tooltip, TooltipProvider } from "./Tooltip";

afterEach(cleanup);

describe("Tooltip", () => {
  test("shows its content when the trigger gets focus", async () => {
    render(
      <TooltipProvider>
        <Tooltip content="Download as image">
          <IconButton label="Download as image">
            <Download />
          </IconButton>
        </Tooltip>
      </TooltipProvider>,
    );
    screen.getByRole("button", { name: "Download as image" }).focus();
    const tip = await screen.findByRole("tooltip", undefined, { timeout: 2000 });
    expect(tip.textContent).toBe("Download as image");
  });
});
