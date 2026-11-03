/**
 * Something is happening and there is nothing to count (docs/design.md).
 *
 * A word saying what is happening, optionally an indeterminate bar, and then
 * the caller replaces the whole thing with the real result sentence. It must
 * never be given steps: inventing them in the client is what D-048 refuses.
 * The word is a live region; the bar is decorative and hidden.
 */

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
