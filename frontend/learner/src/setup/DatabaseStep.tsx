import { useDatabaseSource } from "@charie/shared";
import { DatabaseForm } from "../sources/DatabaseForm";

// Step 1: connect the database. Continue saves when the form changed, and
// just moves on when a saved source is already there.
export function DatabaseStep({ onDone }: { onDone: () => void }) {
  const source = useDatabaseSource();
  return (
    <section aria-label="Connect your database">
      <h2 className="font-serif text-[24px] font-semibold">Connect your database</h2>
      <p className="mt-1.5 text-[14.5px] text-muted">
        Charie only reads your data. Use a login that can&rsquo;t change anything; Charie checks
        this too.
      </p>
      <div className="mt-5">
        {source.isPending ? (
          <p className="text-[14px] text-muted" role="status">
            Loading the saved connection…
          </p>
        ) : source.isError ? (
          <p className="text-[14px] text-muted" role="alert">
            Couldn&rsquo;t load the saved connection.{" "}
            <button
              type="button"
              className="font-medium text-accent-ink underline-offset-2 hover:underline"
              onClick={() => void source.refetch()}
            >
              Try again
            </button>
          </p>
        ) : (
          <DatabaseForm
            key={source.data.source ? "saved" : "empty"}
            initial={source.data.source}
            submitLabel="Continue"
            onSubmitted={onDone}
          />
        )}
      </div>
    </section>
  );
}
