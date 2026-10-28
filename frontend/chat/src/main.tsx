import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { fontsReady } from "@charie/shared";
import App from "./App";
import "./index.css";

void fontsReady();

const KIT_ENABLED = import.meta.env.DEV || import.meta.env.VITE_MOCK === "1";
const KitPage = KIT_ENABLED ? lazy(() => import("./kit/KitPage")) : null;
const showKit = KIT_ENABLED && KitPage && window.location.pathname.startsWith("/__kit");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Suspense fallback={null}>{showKit && KitPage ? <KitPage /> : <App />}</Suspense>
  </StrictMode>,
);
