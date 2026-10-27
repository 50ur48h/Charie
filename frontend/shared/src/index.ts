export function appName(app: "chat" | "learner"): string {
  return app === "learner" ? "Charie Learner" : "Charie";
}
