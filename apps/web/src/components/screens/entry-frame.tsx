/** The frame for the screens a person sees before they are inside an organization. */

import { CircleAlert, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { BrandMark, Wordmark } from "@/components/shell/brand";
import { cn } from "@/lib/utils";

export function EntryFrame({
  children,
  footer,
  wide = false,
}: {
  children: ReactNode;
  /** Pinned to the foot of the page, below the centred column. */
  footer?: ReactNode | undefined;
  /** For the bootstrap profile, which holds lists rather than one small form. */
  wide?: boolean | undefined;
}) {
  return (
    <main className="relative isolate flex min-h-dvh flex-col items-center px-5 pt-12 pb-8 sm:pt-16">
      {/* A soft wash of the palette's accent behind the mark. Decorative. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[460px] bg-[radial-gradient(55%_100%_at_50%_0%,var(--accent-soft),transparent)]"
      />
      <div
        className={cn(
          "my-auto flex w-full animate-fade-up flex-col gap-8",
          wide ? "max-w-[560px]" : "max-w-[400px]",
        )}
      >
        {children}
      </div>
      {footer && <div className="mt-10 w-full max-w-[560px]">{footer}</div>}
    </main>
  );
}

/** The mark and the wordmark, large on the front door and smaller elsewhere. */
export function EntryBrand({
  size = "large",
  heading = false,
  wordmark: withWordmark = true,
  children,
}: {
  size?: "large" | "small" | undefined;
  /** The wordmark is the page's title, when nothing else on the page is. */
  heading?: boolean | undefined;
  /** Off where the page's own title already says the product's name. */
  wordmark?: boolean | undefined;
  /** A line under the wordmark, such as the product's one-line pitch. */
  children?: ReactNode | undefined;
}) {
  const large = size === "large";
  const wordmark = <Wordmark className={large ? "text-[34px]" : "text-[24px]"} />;
  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <BrandMark
        className={cn(
          "text-brand drop-shadow-[0_8px_18px_rgba(var(--shadow-rgb),.14)]",
          large ? "size-14" : "size-10",
        )}
      />
      {withWordmark && (heading ? <h1>{wordmark}</h1> : wordmark)}
      {children && (
        <p className="max-w-[52ch] text-[15.5px] leading-relaxed text-balance text-muted-foreground">
          {children}
        </p>
      )}
    </div>
  );
}

/** A short message inside a card, in the colour of what it reports. */
export function Notice({ tone, children }: { tone: "bad" | "warn"; children: ReactNode }) {
  const Icon = tone === "bad" ? CircleAlert : TriangleAlert;
  return (
    <p
      role={tone === "bad" ? "alert" : undefined}
      className={cn(
        "flex items-start gap-2 rounded-md px-3 py-2.5 text-[13px] leading-relaxed",
        tone === "bad" ? "bg-bad-soft text-bad-ink" : "bg-warn-soft text-warn-ink",
      )}
    >
      <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <span className="min-w-0">{children}</span>
    </p>
  );
}
