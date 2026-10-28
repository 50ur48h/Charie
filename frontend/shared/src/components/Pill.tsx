import type { LucideIcon } from "lucide-react";
import { cn } from "./cn";

const pillTones = {
  neutral: "",
  accent: "bg-accent-soft text-accent-ink",
  good: "bg-good-soft text-good-ink",
  bad: "bg-bad-soft text-bad-ink",
  warn: "bg-warn-soft text-warn-ink",
  outline: "border border-border bg-transparent",
} as const;

export type PillTone = keyof typeof pillTones;

export function Pill({
  tone = "neutral",
  icon: Icon,
  className,
  children,
}: {
  tone?: PillTone;
  icon?: LucideIcon;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-[26px] items-center gap-1.5 whitespace-nowrap rounded-full bg-surface-2 px-2.5 text-[12.5px] font-medium text-text-2 [--icon:14px]",
        pillTones[tone],
        className,
      )}
    >
      {Icon && <Icon aria-hidden="true" />}
      {children}
    </span>
  );
}

const dotTones = {
  neutral: "bg-muted-2",
  good: "bg-good shadow-[0_0_0_3px_var(--good-soft)]",
  warn: "bg-warn shadow-[0_0_0_3px_var(--warn-soft)]",
  bad: "bg-bad shadow-[0_0_0_3px_var(--bad-soft)]",
} as const;

export function StatusDot({ tone = "neutral", className }: { tone?: keyof typeof dotTones; className?: string }) {
  return (
    <span aria-hidden="true" className={cn("size-2 flex-none rounded-full", dotTones[tone], className)} />
  );
}
