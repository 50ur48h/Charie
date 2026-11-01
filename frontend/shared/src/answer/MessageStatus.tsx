import { cn } from "../components/cn";

export function MessageStatus({ status }: { status: "stopped" | "failed" }) {
  const text =
    status === "stopped"
      ? "I stopped before finishing. Ask again to get an answer."
      : "Something went wrong while answering. Please ask again.";
  return (
    <p className={cn("text-[14px]", status === "stopped" ? "text-muted" : "text-danger")}>
      {text}
    </p>
  );
}
