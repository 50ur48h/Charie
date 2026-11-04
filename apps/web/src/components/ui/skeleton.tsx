/** What a list looks like before its rows arrive (docs/design.md, Waiting). */

import { cn } from "@/lib/utils";

const bar =
  "block h-3 rounded-full bg-[linear-gradient(90deg,var(--surface-2)_25%,var(--border-soft)_50%,var(--surface-2)_75%)] bg-[length:200%_100%] animate-shimmer";

export function SkeletonList({
  rows = 3,
  avatar = false,
  label,
}: {
  /** Roughly what usually arrives. Round down. */
  rows?: number;
  /** A leading circle, for lists whose rows carry an avatar or a status dot. */
  avatar?: boolean;
  /** What is being waited for, e.g. "Loading your chats". Announced once. */
  label: string;
}) {
  return (
    <div className="grid gap-1">
      <span role="status" className="sr-only">
        {label}
      </span>
      {Array.from({ length: rows }, (_, index) => (
        <div className="flex items-center gap-3 px-3 py-2" key={index} aria-hidden="true">
          {avatar && <span className={cn(bar, "size-7 shrink-0 rounded-full")} />}
          {/* Uneven widths, because real rows are uneven. */}
          <span className={cn(bar, index % 3 === 0 ? "w-4/5" : "w-3/5")} />
        </div>
      ))}
    </div>
  );
}
