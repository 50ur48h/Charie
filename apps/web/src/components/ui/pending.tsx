/** Something is happening and there is nothing to count (docs/design.md). */

export function Pending({
  children,
  bar = false,
  spinner = true,
}: {
  /** What is happening, in words. "Reading the schema…" */
  children: string;
  /** An indeterminate bar, for an operation worth showing at full width. */
  bar?: boolean;
  spinner?: boolean;
}) {
  return (
    <div className="grid gap-2">
      <p className="flex items-center gap-2.5 text-[14px] text-muted-foreground">
        {spinner && (
          <span
            aria-hidden="true"
            className="inline-block size-3.5 shrink-0 animate-spin rounded-full border-2 border-brand-soft border-t-brand"
          />
        )}
        <span aria-live="polite">{children}</span>
      </p>
      {bar && (
        <span aria-hidden="true" className="relative block h-1 overflow-hidden rounded-full bg-surface-2">
          <span className="absolute inset-y-0 w-1/3 animate-indeterminate rounded-full bg-brand" />
        </span>
      )}
    </div>
  );
}
