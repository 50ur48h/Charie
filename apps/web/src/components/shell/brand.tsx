import { cn } from "@/lib/utils";

/**
 * Charie's mark: a rounded tile holding a "D" with a data point at its heart.
 * Drawn in `currentColor`, so it takes the palette's accent wherever it sits.
 */
export function BrandMark({ className }: { className?: string | undefined }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("block shrink-0", className)}>
      <rect width="32" height="32" rx="9" fill="currentColor" />
      <path
        d="M11.2 9.6h4.6a6.4 6.4 0 0 1 0 12.8h-4.6z"
        fill="none"
        stroke="#fff"
        strokeWidth="2.6"
        strokeLinejoin="round"
      />
      <circle cx="16.2" cy="16" r="1.9" fill="#fff" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string | undefined }) {
  return (
    <span
      className={cn(
        "font-serif text-[23px] leading-none font-semibold tracking-[-0.01em] text-text",
        className,
      )}
    >
      Charie
    </span>
  );
}
