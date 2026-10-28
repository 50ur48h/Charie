import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: [
      {
        find: "msw/browser",
        replacement: fileURLToPath(new URL("./test/stubs/msw-browser.ts", import.meta.url)),
      },
      {
        find: "@charie/shared/mocks",
        replacement: fileURLToPath(new URL("./shared/src/mocks/index.ts", import.meta.url)),
      },
      {
        find: "@charie/shared",
        replacement: fileURLToPath(new URL("./shared/src/index.ts", import.meta.url)),
      },
    ],
  },
  test: {
    environment: "jsdom",
    exclude: ["**/node_modules/**", "**/dist/**", "**/dist-mock/**", "e2e/**"],
    setupFiles: ["./shared/src/testSetup.ts"],
  },
});
