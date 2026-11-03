import { Lightbulb } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const TONES = {
  warn: { box: "bg-warn-soft", icon: "text-warn", title: "text-warn-ink" },
  bad: { box: "bg-bad-soft", icon: "text-bad", title: "text-bad-ink" },
  good: { box: "bg-good-soft", icon: "text-good", title: "text-good-ink" },
  note: { box: "bg-surface-2", icon: "text-brand", title: "text-text" },
} as const;

/** A quiet aside inside an answer (design: `.a-callout`, "Worth knowing"). */
export function Callout({
  tone = "warn",
  icon,
  title,
  children,
  label,
}: {
  tone?: keyof typeof TONES;
  icon?: ReactNode;
  title: string;
  children: ReactNode;
  /** An accessible name for the region, when the title is not enough. */
  label?: string | undefined;
}) {
  const colours = TONES[tone];
  return (
    <aside
      aria-label={label ?? title}
      className={cn("flex animate-fade-up gap-3 rounded-lg px-4 py-3.5 font-sans", colours.box)}
    >
      <span aria-hidden="true" className={cn("grid h-[22px] place-items-center [&_svg]:size-[18px]", colours.icon)}>
        {icon ?? <Lightbulb />}
      </span>
      <div className="min-w-0 flex-1">
        <p className={cn("mb-0.5 text-[14px] font-semibold", colours.title)}>{title}</p>
        <div className="font-serif text-[16.5px] leading-[1.6] text-prose">{children}</div>
      </div>
    </aside>
  );
}
