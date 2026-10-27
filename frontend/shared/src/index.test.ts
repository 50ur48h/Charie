import { describe, expect, it } from "vitest";
import { appName } from "./index";

describe("appName", () => {
  it("returns the right names", () => {
    expect(appName("chat")).toBe("Charie");
    expect(appName("learner")).toBe("Charie Learner");
  });
});
