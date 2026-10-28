import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@charie/shared": fileURLToPath(new URL("./shared/src/index.ts", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    exclude: ["**/node_modules/**", "**/dist/**", "**/dist-mock/**", "e2e/**"],
    setupFiles: ["./shared/src/testSetup.ts"],
  },
});
