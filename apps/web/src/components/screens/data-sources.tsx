"use client";

/** Registering the databases an organization wants analysed (plan WP3.4). */

import {
  BookMarked,
  ChevronDown,
  CircleAlert,
  Clock,
  Database,
  Info,
  KeyRound,
  Lock,
  MessageSquareText,
  PlugZap,
  RefreshCw,
  ScanSearch,
  ShieldAlert,
  ShieldCheck,
  Table2,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useState, type ReactNode } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input, controlClass } from "@/components/ui/input";
import { Pending } from "@/components/ui/pending";
import { SkeletonList } from "@/components/ui/skeleton";
import { Hint } from "@/components/ui/tooltip";
import {
  createApi,
  type ActiveDataSource,
  type DataSource,
  type ProfileResult,
  type RefreshResult,
  type TestResult,
} from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

const ENGINES = ["pg", "mssql"] as const;

/** Mirrors the API's `TlsMode`. Ordered weakest first, as the ladder reads. */
const TLS_MODES = ["prefer", "require", "verify-ca", "verify-full"] as const;

const ENGINE_NAMES: Record<string, string> = {
  pg: "PostgreSQL",
  mssql: "SQL Server",
};

const ENGINE_OPTIONS = ENGINES.map((engine) => ({
  value: engine,
  label: ENGINE_NAMES[engine] ?? engine,
}));

/** The empty choice is a real one: it defers to this deployment's TLS policy. */
const TLS_OPTIONS = [
  { value: "", label: "Deployment policy" },
  ...TLS_MODES.map((mode) => ({ value: mode, label: mode })),
];

const STATUS_TONES: Record<string, Tone> = {
  verified: "mint",
  error: "rose",
  registered: "neutral",
};

const DEFAULT_PORTS: Record<string, string> = { pg: "5432", mssql: "1433" };

interface Draft {
  name: string;
  engine: string;
  host: string;
  port: string;
  database: string;
  username: string;
  password: string;
  tlsMode: string;
}

const EMPTY: Draft = {
  name: "",
  engine: "pg",
  host: "",
  port: DEFAULT_PORTS.pg ?? "5432",
  database: "",
  username: "",
  password: "",
  tlsMode: "",
};

function statusWord(source: DataSource): string {
  if (source.status === "verified") return "read-only verified";
  if (source.status === "error") return "not usable";
  return "not checked yet";
}

function when(timestamp: string | null): string {
  if (!timestamp) return "never";
  const parsed = new Date(timestamp);
  return Number.isNaN(parsed.getTime()) ? timestamp : parsed.toLocaleString();
}

const CALLOUT_TONES = {
  brand: { box: "bg-brand-soft/70 text-text-2", icon: "text-brand-ink" },
  neutral: { box: "bg-surface-2 text-text-2", icon: "text-muted-foreground" },
  warn: { box: "bg-warn-soft text-text-2", icon: "text-warn-ink" },
  bad: { box: "bg-bad-soft text-bad-ink", icon: "text-bad-ink" },
} as const;

/** A soft, tinted note: a result, a choice, or something to act on. */
function Callout({
  tone,
  icon,
  children,
  className,
}: {
  tone: keyof typeof CALLOUT_TONES;
  icon: ReactNode;
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <div
      className={cn(
        "flex animate-fade-up items-start gap-3 rounded-md px-4 py-3 text-[13.5px] leading-relaxed",
        CALLOUT_TONES[tone].box,
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn("mt-[3px] shrink-0 [&_svg]:size-4", CALLOUT_TONES[tone].icon)}
      >
        {icon}
      </span>
      <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">{children}</div>
    </div>
  );
}

/** A native select whose options read as words, for the two choices that have codes. */
function Choice({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div className="grid gap-1.5">
      <label className="text-[13px] font-medium text-text-2" htmlFor={id}>
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          className={cn(controlClass, "cursor-pointer appearance-none pr-9")}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
        />
      </div>
    </div>
  );
}

/** What a test found, said plainly and without rounding anything up. */
function Result({ result }: { result: TestResult }) {
  const proven = result.readonly_verified;
  return (
    // A failed check is a normal outcome with a next step, not an alarm: the same layout as a pass.
    <div
      className={cn(
        "animate-fade-up rounded-md px-4 py-3.5 text-[13.5px]",
        proven ? "bg-good-soft" : "bg-warn-soft",
      )}
    >
      <div className={cn("flex items-start gap-3", proven ? "text-good-ink" : "text-warn-ink")}>
        {proven ? (
          <ShieldCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        ) : (
          <ShieldAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        )}
        <p className="font-semibold [overflow-wrap:anywhere]">{result.detail}</p>
      </div>
      <dl className="mt-2.5 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-5 gap-y-1 pl-7 text-[13px] text-text-2">
        <dt>Reachable</dt>
        <dd className="font-medium text-text">{result.reachable ? "yes" : "no"}</dd>
        <dt>Read-only</dt>
        <dd className="font-medium text-text">{result.readonly_verified ? "proven" : "not proven"}</dd>
        {result.tls_detail && (
          <>
            <dt>Encryption</dt>
            <dd className="text-text [overflow-wrap:anywhere]">{result.tls_detail}</dd>
          </>
        )}
        {result.server_version && (
          <>
            <dt>Server</dt>
            <dd className="text-text [overflow-wrap:anywhere]">{result.server_version}</dd>
          </>
        )}
        <dt>Checked</dt>
        <dd className="text-text">{when(result.checked_at)}</dd>
      </dl>
      {result.evidence.length > 0 && (
        <ul className="mt-2.5 ml-7 list-disc space-y-0.5 pl-4 text-[13px] text-text-2 marker:text-muted-foreground">
          {result.evidence.map((note) => (
            <li key={note} className="[overflow-wrap:anywhere]">
              {note}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function DataSources({ orgId, role }: { orgId: string; role: string | null }) {
  const session = useSession();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  // Unknown role means no admin controls.
  const isAdmin = role === "admin";
  // Reading a database into the catalog is Contributor work.
  const canRefresh = isAdmin || role === "contributor";

  const [sources, setSources] = useState<DataSource[] | null>(null);
  // : Which database this organization answers questions from (D-045).
  const [active, setActive] = useState<ActiveDataSource | null>(null);
  const [error, setError] = useState<string | null>(null);
  // : Where the current error belongs: a source's id, "register", or null for.
  const [errorAt, setErrorAt] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, TestResult>>({});
  const [catalogNotes, setCatalogNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [rotating, setRotating] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const load = useCallback(async () => {
    const [registered, chosen] = await Promise.all([
      api.dataSources(orgId),
      api.activeDataSource(orgId),
    ]);
    setSources(registered);
    setActive(chosen);
  }, [api, orgId]);

  useEffect(() => {
    // Guarded so a slow response cannot write into an unmounted screen.
    let alive = true;
    void (async () => {
      try {
        const [registered, chosen] = await Promise.all([
          api.dataSources(orgId),
          api.activeDataSource(orgId),
        ]);
        if (!alive) return;
        setSources(registered);
        setActive(chosen);
      } catch (cause) {
        if (alive) setError(cause instanceof Error ? cause.message : "Could not load");
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, orgId]);

  /** What is happening, and to which source, while a one-shot request is out. */
  const [pending, setPending] = useState<{ id: string; what: string } | null>(null);

  const run = async (
    action: () => Promise<void>,
    doing?: { id: string; what: string },
    anchor: string | null = doing?.id ?? null,
  ) => {
    setBusy(true);
    setError(null);
    setErrorAt(null);
    if (doing) setPending(doing);
    try {
      await action();
      await load();
    } catch (cause) {
      // The API's own words. "TLS mode 'prefer' allows an unencrypted connection…" names the fix.
      setError(cause instanceof Error ? cause.message : "That did not work");
      setErrorAt(anchor);
    } finally {
      setBusy(false);
      setPending(null);
    }
  };

  const register = (event: React.FormEvent) => {
    event.preventDefault();
    const submitted = draft;
    void run(
      async () => {
        try {
          await api.registerDataSource(orgId, {
            name: submitted.name.trim(),
            engine: submitted.engine,
            host: submitted.host.trim(),
            port: Number(submitted.port),
            database: submitted.database.trim(),
            username: submitted.username.trim(),
            password: submitted.password,
            ...(submitted.tlsMode ? { tls_mode: submitted.tlsMode } : {}),
          });
          setDraft(EMPTY);
        } finally {
          // Whatever happened.
          setDraft((current) => ({ ...current, password: "" }));
        }
      },
      undefined,
      "register",
    );
  };

  const rotate = (source: DataSource) => {
    const submitted = newPassword;
    void run(
      async () => {
        try {
          await api.rotateCredentials(orgId, source.id, { password: submitted });
          setRotating(null);
        } finally {
          setNewPassword("");
        }
      },
      undefined,
      source.id,
    );
  };

  const test = (source: DataSource) =>
    void run(
      async () => {
        const result = await api.testDataSource(orgId, source.id);
        setResults((current) => ({ ...current, [source.id]: result }));
      },
      { id: source.id, what: "Connecting, and checking the login cannot write…" },
    );

  const note = (source: DataSource, said: RefreshResult | ProfileResult) =>
    setCatalogNotes((current) => ({ ...current, [source.id]: said.detail }));

  const refresh = (source: DataSource) =>
    void run(
      async () => {
        note(source, await api.refreshCatalog(orgId, source.id));
      },
      { id: source.id, what: "Reading the schema…" },
    );

  const profileSource = (source: DataSource) =>
    void run(
      async () => {
        note(source, await api.profileCatalog(orgId, source.id));
      },
      { id: source.id, what: "Profiling the columns…" },
    );

  /** `from` is the source whose control was pressed, so a refusal renders there. */
  const choose = (source: DataSource | null, from: DataSource) =>
    run(
      async () => {
        await api.setActiveDataSource(orgId, source?.id ?? null);
      },
      undefined,
      from.id,
    );

  const remove = (source: DataSource) =>
    void run(() => api.removeDataSource(orgId, source.id), undefined, source.id);

  // : `null` while still loading, so nothing claims "no database is chosen".
  const chosenId = active?.data_source_id ?? null;

  const failure = (message: string) => (
    <Callout tone="bad" icon={<CircleAlert />}>
      <p role="alert">{message}</p>
    </Callout>
  );

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      {/* Which database answers questions. */}
      {active !== null &&
        (chosenId === null ? (
          <Callout tone="warn" icon={<TriangleAlert />}>
            <p>
              {isAdmin
                ? "No database is chosen yet, so questions have nowhere to go. Choose one below."
                : "No database is chosen yet, so questions have nowhere to go. An Admin can choose one."}
            </p>
          </Callout>
        ) : (
          <Callout tone="brand" icon={<MessageSquareText />}>
            <p>
              Questions are answered from{" "}
              <strong className="font-semibold text-text">{active.data_source_name}</strong>.
            </p>
          </Callout>
        ))}

      {!isAdmin && (
        <p className="flex items-start gap-2 text-[13px] leading-relaxed text-muted-foreground">
          <Lock aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          These are the databases this organization can ask questions about. Only an Admin can
          add or change them.
        </p>
      )}

      {error && errorAt === null && failure(error)}

      {sources === null && !error && (
        <div className="rounded-lg border border-border bg-surface p-3 shadow-[0_1px_2px_rgba(var(--shadow-rgb),.05)]">
          <SkeletonList rows={2} avatar label="Loading data sources" />
        </div>
      )}

      {sources?.length === 0 && (
        <EmptyState
          icon={<Database />}
          title="No databases registered"
          /* The Reader gets the sentence, not a control the API would refuse (B-008). */
          action={isAdmin ? undefined : <span>An Admin can register one.</span>}
        >
          {isAdmin
            ? "Register one below and this organization can start asking questions of it. Use a login that can only read."
            : "Once one is registered, this organization can start asking questions of it."}
        </EmptyState>
      )}

      {sources && sources.length > 0 && (
        <ul className="grid gap-4">
          {sources.map((source, index) => {
            const chosen = source.id === chosenId;
            const result = results[source.id];
            const said = catalogNotes[source.id];
            return (
              <li
                key={source.id}
                className="animate-fade-up overflow-hidden rounded-lg border border-border bg-surface shadow-[0_1px_2px_rgba(var(--shadow-rgb),.05)]"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <div className="grid gap-4 p-5 sm:p-6">
                  <div className="flex items-start gap-3.5">
                    <span
                      aria-hidden="true"
                      className={cn(
                        "grid size-10 shrink-0 place-items-center rounded-md [&_svg]:size-5",
                        chosen ? "bg-brand text-on-brand" : "bg-brand-soft text-brand-ink",
                      )}
                    >
                      <Database />
                    </span>
                    <div className="flex min-w-0 flex-1 flex-wrap items-start justify-between gap-x-4 gap-y-1">
                      <div className="min-w-0">
                        <h3 className="font-serif text-[17px] leading-snug font-semibold text-text">
                          {source.name}
                        </h3>
                        <p className="mt-0.5 font-mono text-[12.5px] text-muted-foreground [overflow-wrap:anywhere]">
                          {source.host_display}
                        </p>
                      </div>
                      {(canRefresh || isAdmin) && (
                        <div className="-ml-2.5 flex flex-wrap items-center gap-0.5 sm:-mr-2 sm:ml-0">
                          <Button asChild variant="ghost" size="sm">
                            <Link href={`/orgs/${orgId}/data-sources/${source.id}/catalog`}>
                              <Table2 />
                              Catalog
                            </Link>
                          </Button>
                          {/* Admin only, because everything behind it is. */}
                          {isAdmin && (
                            <Button asChild variant="ghost" size="sm">
                              <Link href={`/orgs/${orgId}/data-sources/${source.id}/definitions`}>
                                <BookMarked />
                                Definitions
                              </Link>
                            </Button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="-mt-1 grid gap-3 sm:pl-[54px]">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge tone="sky">{ENGINE_NAMES[source.engine] ?? source.engine}</Badge>
                      <Badge tone={STATUS_TONES[source.status] ?? "neutral"}>
                        {statusWord(source)}
                      </Badge>
                      {/* The mode, not a tick: `require` encrypts and verifies nothing. */}
                      <Badge tone={source.tls_mode === "prefer" ? "peach" : "lilac"}>
                        TLS: {source.tls_mode}
                      </Badge>
                      {/* A word, not a colour: design.md forbids colour carrying meaning alone. */}
                      {chosen && (
                        <Badge tone="mint">
                          <MessageSquareText aria-hidden="true" className="size-3" />
                          Answers questions
                        </Badge>
                      )}
                    </div>

                    <dl className="flex flex-wrap gap-x-6 gap-y-1.5 text-[13px] leading-relaxed">
                      <div>
                        <dt className="inline text-muted-foreground">
                          <KeyRound aria-hidden="true" className="mr-1.5 inline size-3.5 align-[-2px]" />
                          Connects as
                        </dt>{" "}
                        <dd className="inline text-text-2">
                          an account ending{" "}
                          <code className="rounded-[5px] bg-surface-2 px-1.5 py-px text-[12px] text-text">
                            {source.username_last4}
                          </code>
                        </dd>
                      </div>
                      <div>
                        <dt className="inline text-muted-foreground">
                          <Clock aria-hidden="true" className="mr-1.5 inline size-3.5 align-[-2px]" />
                          Last proven read-only
                        </dt>{" "}
                        <dd className="inline text-text-2">{when(source.last_verified_at)}</dd>
                      </div>
                    </dl>
                  </div>

                  {pending?.id === source.id ? (
                    <div className="rounded-md bg-surface-2/70 px-4 py-3">
                      <Pending bar>{pending.what}</Pending>
                    </div>
                  ) : (
                    <>
                      {result && <Result result={result} />}
                      {said && (
                        <Callout tone="neutral" icon={<Info />}>
                          <p>{said}</p>
                        </Callout>
                      )}
                    </>
                  )}

                  {error && errorAt === source.id && failure(error)}
                </div>

                {(canRefresh || isAdmin) && (
                  <div className="flex flex-wrap items-center gap-2 border-t border-border-soft bg-surface-2/40 px-5 py-3 sm:px-6">
                    {/* The choice D-045 moved here. */}
                    {isAdmin &&
                      (chosen ? (
                        <Button size="sm" disabled={busy} onClick={() => choose(null, source)}>
                          Stop answering from this
                        </Button>
                      ) : (
                        <Button
                          variant="primary"
                          size="sm"
                          disabled={busy}
                          onClick={() => choose(source, source)}
                        >
                          <MessageSquareText />
                          Answer questions from this
                        </Button>
                      ))}
                    {isAdmin && (
                      <Button size="sm" disabled={busy} onClick={() => test(source)}>
                        <PlugZap />
                        Test connection
                      </Button>
                    )}
                    {canRefresh && (
                      <>
                        <Button size="sm" disabled={busy} onClick={() => refresh(source)}>
                          <RefreshCw />
                          Refresh catalog
                        </Button>
                        <Button size="sm" disabled={busy} onClick={() => profileSource(source)}>
                          <ScanSearch />
                          Profile columns
                        </Button>
                      </>
                    )}
                    {isAdmin && (
                      <div className="ml-auto flex items-center gap-0.5">
                        <Hint label="Rotate password">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Rotate password"
                            aria-expanded={rotating === source.id}
                            className="aria-expanded:bg-surface-2 aria-expanded:text-text"
                            disabled={busy}
                            onClick={() => {
                              setNewPassword("");
                              setRotating(rotating === source.id ? null : source.id);
                            }}
                          >
                            <KeyRound />
                          </Button>
                        </Hint>
                        <Hint label="Remove">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Remove"
                            className="hover:bg-bad-soft hover:text-bad-ink"
                            disabled={busy}
                            onClick={() => remove(source)}
                          >
                            <Trash2 />
                          </Button>
                        </Hint>
                      </div>
                    )}
                  </div>
                )}

                {isAdmin && rotating === source.id && (
                  <form
                    className="grid animate-fade-up gap-2.5 border-t border-border-soft bg-surface-2/60 px-5 py-4 sm:px-6"
                    onSubmit={(event) => {
                      event.preventDefault();
                      rotate(source);
                    }}
                  >
                    <div className="flex flex-wrap items-end gap-3">
                      <div className="min-w-[220px] flex-1 sm:max-w-sm">
                        <Input
                          label="New password"
                          type="password"
                          autoComplete="new-password"
                          value={newPassword}
                          onChange={(event) => setNewPassword(event.target.value)}
                        />
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="primary"
                          type="submit"
                          className="h-10"
                          disabled={busy || !newPassword}
                        >
                          Save
                        </Button>
                        <Button
                          variant="ghost"
                          className="h-10"
                          disabled={busy}
                          onClick={() => {
                            setNewPassword("");
                            setRotating(null);
                          }}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                    <p className="text-[12.5px] leading-relaxed text-muted-foreground">
                      Rotating retires the read-only verification until the connection is tested
                      again.
                    </p>
                  </form>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {isAdmin && (
        <Card
          title="Register a database"
          subtitle="Use a login that can only read. The password is stored encrypted, outside this application's database, and is never shown again."
        >
          <form onSubmit={register} className="grid gap-5">
            <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
              <Input
                label="Name"
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                placeholder="Pizza demo"
              />
              <Choice
                label="Engine"
                options={ENGINE_OPTIONS}
                value={draft.engine}
                onChange={(engine) =>
                  setDraft({
                    ...draft,
                    engine,
                    port: DEFAULT_PORTS[engine] ?? draft.port,
                  })
                }
              />
              <Input
                label="Host"
                value={draft.host}
                onChange={(event) => setDraft({ ...draft, host: event.target.value })}
                placeholder="localhost"
              />
              <Input
                label="Port"
                type="number"
                value={draft.port}
                onChange={(event) => setDraft({ ...draft, port: event.target.value })}
              />
              <Input
                label="Database"
                value={draft.database}
                onChange={(event) => setDraft({ ...draft, database: event.target.value })}
                placeholder="pizza"
              />
              <Input
                label="Username"
                autoComplete="off"
                value={draft.username}
                onChange={(event) => setDraft({ ...draft, username: event.target.value })}
                placeholder="pizza_readonly"
              />
              <Input
                label="Password"
                type="password"
                autoComplete="new-password"
                value={draft.password}
                onChange={(event) => setDraft({ ...draft, password: event.target.value })}
              />
              <Choice
                label="Encryption"
                options={TLS_OPTIONS}
                value={draft.tlsMode}
                onChange={(tlsMode) => setDraft({ ...draft, tlsMode })}
              />
            </div>

            {error && errorAt === "register" && failure(error)}

            <div className="flex flex-col gap-4 border-t border-border-soft pt-5 sm:flex-row sm:items-center sm:justify-between">
              <p className="max-w-[58ch] text-[12.5px] leading-relaxed text-muted-foreground">
                Leave Encryption on Deployment policy to use this deployment&rsquo;s rule: TLS is
                required for any database that is not on the server itself. The password field is
                cleared when you submit, whether it worked or not.
              </p>
              <Button
                variant="primary"
                type="submit"
                className="shrink-0 self-start sm:self-auto"
                disabled={
                  busy ||
                  !draft.name.trim() ||
                  !draft.host.trim() ||
                  !draft.database.trim() ||
                  !draft.username.trim() ||
                  !draft.password
                }
              >
                <Database />
                {busy ? "Registering…" : "Register"}
              </Button>
            </div>
          </form>
        </Card>
      )}
    </div>
  );
}
