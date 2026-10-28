import { cn } from "./cn";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "rounded-[8px] bg-[linear-gradient(90deg,var(--surface-2)_25%,var(--head-hover)_50%,var(--surface-2)_75%)] bg-[length:200%_100%] animate-[shimmer_1.6s_linear_infinite]",
        className,
      )}
    />
  );
}
