"use client";

/** Number cards (design: `.a-kpis`), for a table that is really a short list of figures. */

import { CircleAlert, Minus, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

import { signedTone } from "./cells";

export interface Kpi {
  label: string;
  value: string;
  delta?: string | undefined;
  note?: string | undefined;
}

interface Parts {
  prefix: string;
  suffix: string;
  target: number;
  decimals: number;
  grouped: boolean;
}

function split(text: string): Parts | null {
  const match = /^(.*?)(-?[\d,]*\.?\d+)(.*)$/.exec(text);
  if (!match) return null;
  const [, prefix = "", digits = "", suffix = ""] = match;
  const target = Number(digits.replace(/,/g, ""));
  if (!Number.isFinite(target)) return null;
  return {
    prefix,
    suffix,
    target,
    decimals: digits.includes(".") ? (digits.split(".")[1]?.length ?? 0) : 0,
    grouped: digits.includes(","),
  };
}

function format(parts: Parts, value: number): string {
  const number = value.toLocaleString("en-US", {
    minimumFractionDigits: parts.decimals,
    maximumFractionDigits: parts.decimals,
    useGrouping: parts.grouped,
  });
  return `${parts.prefix}${number}${parts.suffix}`;
}

function reducedMotion(): boolean {
  return typeof window !== "undefined" && (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false);
}

function CountUp({ text }: { text: string }) {
  const [shown, setShown] = useState(() => {
    const parts = split(text);
    return parts && typeof window !== "undefined" && !reducedMotion() ? format(parts, 0) : text;
  });

  useEffect(() => {
    const parts = split(text);
    let frame = 0;
    if (!parts || reducedMotion()) {
      frame = requestAnimationFrame(() => setShown(text));
      return () => cancelAnimationFrame(frame);
    }
    const begin = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - begin) / 1000);
      const eased = 1 - Math.pow(1 - progress, 3);
      setShown(progress < 1 ? format(parts, parts.target * eased) : text);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [text]);

  return <>{shown}</>;
}

export function KpiGrid({ items }: { items: Kpi[] }) {
  return (
    <div
      className={cn(
        "grid gap-3 font-sans [container-type:inline-size]",
        items.length >= 4 ? "grid-cols-2 sm:grid-cols-4" : items.length === 3 ? "grid-cols-1 sm:grid-cols-3" : "grid-cols-2",
      )}
    >
      {items.map((item, index) => {
        const trend = item.delta ? signedTone(item.delta) : null;
        const Icon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : item.delta ? CircleAlert : Minus;
        return (
          <div
            key={`${item.label}-${index}`}
            className="relative min-w-0 animate-fade-up overflow-hidden rounded-lg border border-border bg-surface px-4 pt-3.5 pb-3 shadow-[0_1px_2px_rgba(var(--shadow-rgb),.05)] [container-type:inline-size]"
            style={{ animationDelay: `${index * 70}ms` }}
          >
            <div className="truncate text-[12.5px] font-medium text-muted-foreground">{item.label}</div>
            <div
              className="mt-1 break-words font-serif leading-tight font-semibold tracking-[-0.01em] text-text tabular-nums"
              style={{ fontSize: `clamp(14px, ${180 / Math.max(1, item.value.length)}cqi, 28px)` }}
              title={item.value}
            >
              <CountUp text={item.value} />
            </div>
            {(item.delta || item.note) && (
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                {item.delta && (
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 text-[12.5px] font-semibold",
                      trend === "up" ? "text-good" : trend === "down" ? "text-bad" : "text-warn",
                    )}
                  >
                    <Icon aria-hidden="true" className="size-3.5" />
                    {item.delta}
                  </span>
                )}
                {item.note && <span className="text-[12px] text-muted-foreground">{item.note}</span>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
