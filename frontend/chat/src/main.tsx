import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { fontsReady } from "@charie/shared";
import App from "./App";
import "./index.css";

void fontsReady();

const KIT_ENABLED = import.meta.env.DEV || import.meta.env.VITE_MOCK === "1";
const KitPage = KIT_ENABLED ? lazy(() => import("./kit/KitPage")) : null;
const ChatFrameDemo = KIT_ENABLED
  ? lazy(() => import("./kit/FrameDemos").then((m) => ({ default: m.ChatFrameDemo })))
  : null;
const LearnerFrameDemo = KIT_ENABLED
  ? lazy(() => import("./kit/FrameDemos").then((m) => ({ default: m.LearnerFrameDemo })))
  : null;

const kitPath = KIT_ENABLED ? window.location.pathname : "";
const KitScreen =
  kitPath === "/__kit/chat-frame"
    ? ChatFrameDemo
    : kitPath === "/__kit/learner-frame"
      ? LearnerFrameDemo
      : kitPath.startsWith("/__kit")
        ? KitPage
        : null;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Suspense fallback={null}>{KitScreen ? <KitScreen /> : <App />}</Suspense>
  </StrictMode>,
);
