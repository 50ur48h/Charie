import { describe, expect, test } from "vitest";
import { checkFile } from "./fileRules";

describe("checkFile", () => {
  test("accepts the 6 kinds", () => {
    for (const name of ["a.docx", "b.pdf", "c.pptx", "d.xlsx", "e.md", "f.txt"]) {
      expect(checkFile({ name, size: 1024 })).toBeNull();
    }
  });

  test("refuses a .exe", () => {
    expect(checkFile({ name: "run.exe", size: 1024 })).toBe(
      "run.exe can't be added. Charie reads Word, PDF, PowerPoint, Excel, Markdown and text files.",
    );
  });

  test("refuses a file over 50 MB", () => {
    expect(checkFile({ name: "big.pdf", size: 50 * 1024 * 1024 + 1 })).toBe(
      "big.pdf is too big. Each file can be up to 50 MB.",
    );
  });
});
