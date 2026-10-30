import { useState } from "react";
import { Check, CircleAlert, Database, Plug, ShieldCheck } from "lucide-react";
import {
  Button,
  Field,
  formatShortCount,
  Input,
  Spinner,
  useSaveDatabase,
  useTestDatabase,
  type ConnectionTest,
  type DatabaseSource,
} from "@charie/shared";
import { shortDate } from "../lib/when";

// The database form (P04.2): picked from the design, reused by the setup
// step and the Sources Edit dialog. The form never holds the saved password;
// an empty password keeps it. Test and submit stay disabled until the server
// address, port, database name and username are filled, plus a password when
// none is saved yet.
export function DatabaseForm({
  initial,
  submitLabel,
  onSubmitted,
  cancel,
}: {
  initial: DatabaseSource | null;
  submitLabel: string;
  onSubmitted: () => void;
  cancel?: React.ReactNode;
}) {
  const [host, setHost] = useState(initial?.host ?? "");
  const [port, setPort] = useState(String(initial?.port ?? 5432));
  const [database, setDatabase] = useState(initial?.database ?? "");
  const [username, setUsername] = useState(initial?.username ?? "");
  const [password, setPassword] = useState("");
  const [result, setResult] = useState<{ ok: true; test: ConnectionTest } | { ok: false; message: string } | null>(null);

  const test = useTestDatabase();
  const save = useSaveDatabase();

  function touch(setter: (value: string) => void): (value: string) => void {
    return (value: string) => {
      setter(value);
      setResult(null);
    };
  }
  const setTouchedHost = touch(setHost);
  const setTouchedPort = touch(setPort);
  const setTouchedDatabase = touch(setDatabase);
  const setTouchedUsername = touch(setUsername);
  const setTouchedPassword = touch(setPassword);

  const filled =
    host.trim() !== "" && port.trim() !== "" && database.trim() !== "" && username.trim() !== "";
  const needsPassword = initial === null;
  const valid = filled && (password !== "" || !needsPassword);
  const dirty =
    initial === null ||
    host !== initial.host ||
    port !== String(initial.port) ||
    database !== initial.database ||
    username !== initial.username ||
    password !== "";

  const busy = test.isPending || save.isPending;

  function runTest(): void {
    setResult(null);
    test.mutate(
      { kind: "postgres", host: host.trim(), port: Number(port), database: database.trim(), username: username.trim(), password },
      {
        onSuccess: (data) => setResult({ ok: true, test: data }),
        onError: (error) => setResult({ ok: false, message: error.message }),
      },
    );
  }

  function submit(): void {
    if (!dirty && initial !== null) {
      onSubmitted();
      return;
    }
    save.mutate(
      { kind: "postgres", host: host.trim(), port: Number(port), database: database.trim(), username: username.trim(), password },
      {
        onSuccess: () => onSubmitted(),
        onError: (error) => setResult({ ok: false, message: error.message }),
      },
    );
  }

  return (
    <div>
      <div className="mb-[18px] flex flex-wrap gap-2.5 max-[640px]:flex-col max-[640px]:*:w-full" role="group" aria-label="Database type">
        <span className="inline-flex items-center gap-2.5 rounded-[14px] border-[1.5px] border-accent bg-surface px-4 py-3 text-[14.5px] font-semibold shadow-[0_0_0_3px_var(--accent-soft)]" aria-current="true">
          <Database aria-hidden="true" className="[--icon:17px] text-accent-ink" />
          Postgres
        </span>
        {(["MySQL", "SQL Server"] as const).map((kind) => (
          <span
            key={kind}
            className="inline-flex cursor-not-allowed items-center gap-2.5 rounded-[14px] border-[1.5px] border-border bg-surface px-4 py-3 text-[14.5px] font-semibold opacity-55"
          >
            <Database aria-hidden="true" className="[--icon:17px] text-muted" />
            <span>
              {kind}
              <br />
              <small className="text-[11.5px] font-medium text-muted">Coming soon</small>
            </span>
          </span>
        ))}
      </div>
      <div className="grid gap-3.5 sm:grid-cols-2">
        <Field label="Server address" htmlFor="db-host" className="sm:col-span-2">
          <Input id="db-host" autoComplete="off" value={host} onChange={(e) => setTouchedHost(e.target.value)} />
        </Field>
        <Field label="Port" htmlFor="db-port">
          <Input id="db-port" inputMode="numeric" value={port} onChange={(e) => setTouchedPort(e.target.value)} />
        </Field>
        <Field label="Database name" htmlFor="db-name">
          <Input id="db-name" autoComplete="off" value={database} onChange={(e) => setTouchedDatabase(e.target.value)} />
        </Field>
        <Field label="Username" htmlFor="db-username">
          <Input id="db-username" autoComplete="username" value={username} onChange={(e) => setTouchedUsername(e.target.value)} />
        </Field>
        <Field
          label="Password"
          htmlFor="db-password"
          hint="Stored safely and never shown again."
        >
          <Input
            id="db-password"
            type="password"
            autoComplete={initial ? "new-password" : "current-password"}
            placeholder={initial ? "Saved. Type a new one to change it." : undefined}
            value={password}
            onChange={(e) => setTouchedPassword(e.target.value)}
          />
        </Field>
      </div>
      <p className="mt-4 flex items-start gap-2 rounded-[12px] bg-good-soft p-[12px_14px] text-[13px] text-good-ink">
        <ShieldCheck aria-hidden="true" className="mt-px flex-none [--icon:17px]" />
        Charie only runs read-only queries, with a time limit on each one.
      </p>
      {result?.ok === true && (
        <div className="mt-3.5 grid gap-2.5 rounded-[14px] border border-border bg-surface-2 p-[14px_16px]" role="status">
          <p className="flex items-center gap-2 text-[14.5px] font-semibold">
            <span className="size-2 rounded-full bg-good shadow-[0_0_0_3px_var(--good-soft)]" aria-hidden="true" />
            Connected
            <span className="text-[13px] font-normal text-muted">· the login is read-only</span>
          </p>
          <p className="flex gap-5 text-[13px]">
            <span><b className="font-serif text-[15px]">{result.test.details.tables}</b> <span className="text-muted">tables</span></span>
            <span><b className="font-serif text-[15px]">{formatShortCount(result.test.details.rows)}</b> <span className="text-muted">rows</span></span>
            <span><b className="font-serif text-[15px]">{result.test.data_through === null ? "Not checked yet" : shortDate(result.test.data_through)}</b> <span className="text-muted">newest data</span></span>
          </p>
        </div>
      )}
      {result?.ok === false && (
        <p role="alert" className="mt-3.5 flex items-start gap-2 rounded-[14px] border border-bad bg-bad-soft p-[14px_16px] text-[14px] font-medium text-bad-ink">
          <CircleAlert aria-hidden="true" className="mt-px flex-none [--icon:17px]" />
          {result.message}
        </p>
      )}
      <div className="mt-6 flex flex-wrap gap-2.5 border-t border-border-soft pt-[18px]">
        <Button variant="outline" disabled={!valid || busy} onClick={runTest}>
          {test.isPending ? (
            <><Spinner label="Testing" /> Testing…</>
          ) : result?.ok === true ? (
            <><Check aria-hidden="true" className="[--icon:16px]" /> Connection works</>
          ) : (
            <><Plug aria-hidden="true" className="[--icon:16px]" /> Test connection</>
          )}
        </Button>
        <span className="ml-auto flex gap-2.5 max-[640px]:ml-0 max-[640px]:w-full max-[640px]:*:flex-1">
          {cancel}
          <Button disabled={!valid || busy} onClick={submit}>
            {save.isPending ? "Saving…" : submitLabel}
          </Button>
        </span>
      </div>
    </div>
  );
}
