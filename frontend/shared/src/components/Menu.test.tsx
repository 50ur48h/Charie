import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Download, Pencil, Trash2 } from "lucide-react";
import { IconButton } from "./Button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "./Menu";

afterEach(cleanup);

describe("Menu", () => {
  test("opens with the keyboard and runs the chosen item", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    render(
      <Menu>
        <MenuTrigger asChild>
          <IconButton label="Chat actions">
            <span aria-hidden="true">···</span>
          </IconButton>
        </MenuTrigger>
        <MenuContent>
          <MenuItem icon={Pencil}>Rename</MenuItem>
          <MenuItem icon={Download}>Download as PDF</MenuItem>
          <MenuSeparator />
          <MenuItem icon={Trash2} tone="danger" onSelect={onDelete}>
            Delete
          </MenuItem>
        </MenuContent>
      </Menu>,
    );
    const trigger = screen.getByRole("button", { name: "Chat actions" });
    trigger.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("menu")).toBeTruthy();
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{Enter}");
    expect(onDelete).toHaveBeenCalledTimes(1);
  });
});
