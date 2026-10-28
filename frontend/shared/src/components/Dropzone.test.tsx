import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Dropzone } from "./Dropzone";

afterEach(cleanup);

const twoFiles = () => [
  new File(["hello"], "notes.md", { type: "text/markdown" }),
  new File(["data"], "sales.xlsx", { type: "application/vnd.ms-excel" }),
];

describe("Dropzone", () => {
  test("sends picked files to onFiles", () => {
    const onFiles = vi.fn();
    const { container } = render(<Dropzone onFiles={onFiles} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: twoFiles() } });
    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0][0].map((f: File) => f.name)).toEqual(["notes.md", "sales.xlsx"]);
  });

  test("sends dropped files to onFiles", () => {
    const onFiles = vi.fn();
    render(<Dropzone onFiles={onFiles} />);
    const zone = screen.getByRole("button", { name: /Drop files here/ });
    fireEvent.drop(zone, { dataTransfer: { files: twoFiles() } });
    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0][0]).toHaveLength(2);
  });

  test("does nothing when disabled", () => {
    const onFiles = vi.fn();
    const { container } = render(<Dropzone onFiles={onFiles} disabled />);
    const zone = screen.getByRole("button", { name: /Drop files here/ });
    fireEvent.drop(zone, { dataTransfer: { files: twoFiles() } });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: twoFiles() } });
    expect(onFiles).not.toHaveBeenCalled();
  });
});
