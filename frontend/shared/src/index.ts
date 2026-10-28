export function appName(app: "chat" | "learner"): string {
  return app === "learner" ? "Charie Learner" : "Charie";
}

export * from "./components/Button";
export * from "./components/Card";
export * from "./components/ChoiceCard";
export * from "./components/DataTable";
export * from "./components/Dialog";
export * from "./components/Dropzone";
export * from "./components/IconBox";
export * from "./components/Input";
export * from "./components/Menu";
export * from "./components/Pill";
export * from "./components/Progress";
export * from "./components/Select";
export * from "./components/Skeleton";
export * from "./components/Slider";
export * from "./components/Spinner";
export * from "./components/StatCard";
export * from "./components/Switch";
export * from "./components/Tabs";
export * from "./components/Textarea";
export * from "./components/Toast";
export * from "./components/Tooltip";
export * from "./theme/fonts";
export * from "./theme/theme";
