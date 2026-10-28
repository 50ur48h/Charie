import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  publicDir: mode === "mock" ? "public-mock" : "public",
  define: {
    "import.meta.env.VITE_MOCK": JSON.stringify(mode === "mock" ? "1" : "0"),
  },
  resolve: {
    alias: [
      {
        find: "@charie/shared/mocks",
        replacement: fileURLToPath(new URL("../shared/src/mocks/index.ts", import.meta.url)),
      },
      {
        find: "@charie/shared",
        replacement: fileURLToPath(new URL("../shared/src/index.ts", import.meta.url)),
      },
    ],
  },
  server: {
    port: 5174,
    proxy: {
      "/api": "http://localhost:8002",
    },
  },
  preview: {
    port: 4174,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
  },
}));
