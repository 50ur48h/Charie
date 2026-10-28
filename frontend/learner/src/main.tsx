import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";
import { AppProviders, fontsReady } from "@charie/shared";
import { routes } from "./routes";
import "./index.css";

void fontsReady();

const IS_MOCK = import.meta.env.VITE_MOCK === "1";

async function start() {
  if (IS_MOCK) {
    // A dynamic import keeps MSW out of the production bundle entirely.
    const { startMockApi } = await import("@charie/shared/mocks");
    await startMockApi();
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <AppProviders>
        <RouterProvider router={createBrowserRouter(routes)} />
      </AppProviders>
    </StrictMode>,
  );
}

void start();
