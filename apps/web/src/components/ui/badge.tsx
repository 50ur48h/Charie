import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type Tone = "mint" | "sky" | "lilac" | "peach" | "rose" | "neutral";

const TONES: Record<Tone, string> = {
  mint: "bg-good-soft text-good-ink",
  sky: "bg-brand-soft text-brand-ink",
  lilac: "bg-info-soft text-info-ink",
  peach: "bg-warn-soft text-warn-ink",
  rose: "bg-bad-soft text-bad-ink",
  neutral: "bg-surface-2 text-text-2",
};

/** Roles and statuses use this and nothing else. */
export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone | undefined;
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] leading-[18px] font-semibold whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Colour never carries meaning alone, so the word is always present too. */
export const ROLE_TONES: Record<string, Tone> = {
  admin: "mint",
  contributor: "sky",
  reader: "lilac",
};
