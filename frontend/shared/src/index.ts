export function appName(app: "chat" | "learner"): string {
  return app === "learner" ? "Charie Learner" : "Charie";
}

export * from "./components/Button";
export * from "./components/Card";
export * from "./components/Input";
export * from "./components/Pill";
export * from "./components/Select";
export * from "./components/Slider";
export * from "./components/Switch";
export * from "./components/Tabs";
export * from "./components/Textarea";
export * from "./theme/fonts";
export * from "./theme/theme";
