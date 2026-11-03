"use client";

import { useEffect, useState } from "react";

import { Pending } from "@/components/ui/pending";
import { ApiError, apiBaseUrl, fetchHealth, type Health } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "healthy"; health: Health }
  | { kind: "unreachable"; message: string };

function Dot({ tone }: { tone: "good" | "bad" }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "size-2 shrink-0 rounded-full ring-[3px]",
        tone === "good" ? "bg-good ring-good-soft" : "bg-bad ring-bad-soft",
      )}
    />
  );
}

/**
 * Walking-skeleton widget: proves the browser can reach the API.
 *
 * Failure is a first-class state here, not a thrown error — an unreachable API
 * during local development is the normal case, and saying so plainly is more
 * useful than an empty page.
 *
 * A quiet status line rather than a card: on the front door it is the footnote,
 * not the point.
 */
export function ApiHealth({ className }: { className?: string | undefined }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    fetchHealth(controller.signal)
      .then((health) => setState({ kind: "healthy", health }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          kind: "unreachable",
          message: error instanceof ApiError ? error.message : "Unexpected error calling the API",
        });
      });

    return () => controller.abort();
  }, []);

  return (
    <section
      aria-labelledby="api-health-heading"
      className={cn(
        "grid justify-items-center gap-1.5 text-center text-[12.5px] leading-5 text-muted-foreground",
        className,
      )}
    >
      <h2 className="sr-only" id="api-health-heading">
        API health
      </h2>

      <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
        {/* The same shimmer the working state uses, so every "something is
            happening" in this product reads the same way. `Pending` carries its
            own live region, so the word is still announced. */}
        {state.kind === "loading" && <Pending>Checking…</Pending>}

        {state.kind === "healthy" && (
          <>
            <p className="inline-flex items-center gap-2 font-medium text-text-2" role="status">
              <Dot tone="good" /> Healthy
            </p>
            <dl className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 before:mr-1.5 before:text-faint before:content-['·']">
                <dt>Version</dt>
                <dd className="font-medium text-text-2 tabular-nums">{state.health.version}</dd>
              </div>
              <div className="flex items-center gap-1.5 before:mr-1.5 before:text-faint before:content-['·']">
                <dt>Commit</dt>
                <dd>
                  <code className="rounded-[6px] bg-surface-2 px-1.5 py-px text-text-2">
                    {state.health.git_sha}
                  </code>
                </dd>
              </div>
            </dl>
          </>
        )}

        {state.kind === "unreachable" && (
          <p className="inline-flex items-center gap-2 font-medium text-bad-ink" role="status">
            <Dot tone="bad" /> Unreachable
          </p>
        )}
      </div>

      {state.kind === "unreachable" && (
        <p className="max-w-[48ch] text-[13px] text-bad-ink">{state.message}</p>
      )}

      <p className="max-w-full">
        {/* One interpolation, so the URL is a single text node in the DOM. */}
        <code className="text-[11.5px] break-all">{`${apiBaseUrl()}/healthz`}</code>
      </p>
    </section>
  );
}
