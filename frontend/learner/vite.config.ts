import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { SAMPLE_PASSWORD } from "../shared/src/mocks/password";

export default defineConfig(({ mode }) => {
  if (mode === "mock") {
    console.log(`Sample data mode. Sign in with the password: ${SAMPLE_PASSWORD}`);
  }
  return ({
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
      // changeOrigin: false keeps the screen's Host, so the API's
      // Origin check sees our own address through the proxy.
      "/api": { target: "http://localhost:8002", changeOrigin: false },
    },
  },
  preview: {
    port: 4174,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
  },
})});
