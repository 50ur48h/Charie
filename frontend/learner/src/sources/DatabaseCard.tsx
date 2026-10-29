import { useState } from "react";
import { Database } from "lucide-react";
import {
  Button,
  Card,
  IconBox,
  Pill,
  StatusDot,
  formatShortCount,
  useDatabaseSource,
  type DatabaseSource,
} from "@charie/shared";
import { shortDate, timeAgo } from "../lib/when";
import { EditDatabaseDialog } from "./EditDatabaseDialog";

// The Sources database card (P04.4). Connected shows the status, facts and
// an Edit dialog (P04.2's form); failed and missing sources show their own
// states. Times are plain English; the host is cut at the first dot.
export function DatabaseCard() {
  const source = useDatabaseSource();
  const [editing, setEditing] = useState(false);

  if (source.isPending) {
    return (
      <Card padded={false} className="p-[20px_22px]">
        <p className="text-[14px] text-muted" role="status">
          Loading the database connection…
        </p>
      </Card>
    );
  }
  if (source.isError || !source.data) {
    return (
      <Card padded={false} className="p-[20px_22px]">
        <p className="text-[14px] text-muted" role="alert">
          Couldn&rsquo;t load the database connection.{" "}
          <button
            type="button"
            className="font-medium text-accent-ink underline-offset-2 hover:underline"
            onClick={() => void source.refetch()}
          >
            Try again
          </button>
        </p>
      </Card>
    );
  }

  const saved = source.data.source;
  if (saved === null) {
    return (
      <Card padded={false} className="flex flex-wrap items-center gap-4 p-[20px_22px]">
        <IconBox icon={Database} tone="plain" size={46} />
        <div className="min-w-[300px] flex-1">
          <b className="text-[16px]">No database connected</b>
          <p className="mt-[3px] text-[12.5px] text-muted">
            Connect one so Charie can learn your data.
          </p>
        </div>
        <Button size="sm" className="ml-auto" onClick={() => setEditing(true)}>
          Connect
        </Button>
        <EditDatabaseDialog open={editing} onOpenChange={setEditing} />
      </Card>
    );
  }

  const connected = saved.status === "connected";
  const shortHost = saved.host.split(".")[0];
  const checked = saved.checked_at !== null ? timeAgo(saved.checked_at) : null;
  const line = connected
    ? checked !== null
      ? `Postgres · ${shortHost} · read-only login · checked ${checked}`
      : `Postgres · ${shortHost} · read-only login`
    : checked !== null
      ? `Postgres · ${shortHost} · read-only login · last check failed ${checked}`
      : `Postgres · ${shortHost} · read-only login · last check failed`;
  return (
    <Card padded={false} className="flex flex-wrap items-center gap-4 p-[20px_22px]">
      <IconBox icon={Database} tone={connected ? "good" : "bad"} size={46} />
      <div className="min-w-[300px] flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <b className="text-[16px]">{saved.name}</b>
          {connected ? (
            <Pill tone="good">
              <StatusDot tone="good" />
              Connected
            </Pill>
          ) : (
            <Pill tone="bad">
              <StatusDot tone="bad" />
              Not connected
            </Pill>
          )}
        </p>
        <p className="mt-[3px] text-[12.5px] text-muted">{line}</p>
      </div>
      <div className="ml-auto flex items-center gap-7">
        <Facts source={saved} />
        <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
          Edit
        </Button>
      </div>
      <EditDatabaseDialog open={editing} onOpenChange={setEditing} />
    </Card>
  );
}

function Facts({ source }: { source: DatabaseSource }) {
  const facts: { value: string; label: string }[] = [
    { value: String(source.details.tables), label: "tables" },
    { value: formatShortCount(source.details.rows), label: "rows" },
  ];
  if (source.data_through !== null) {
    facts.push({ value: shortDate(source.data_through), label: "newest data" });
  }
  return (
    <div className="flex gap-7 whitespace-nowrap">
      {facts.map((fact) => (
        <div key={fact.label}>
          <b className="block font-serif text-[20px]">{fact.value}</b>
          <span className="text-[12px] text-muted">{fact.label}</span>
        </div>
      ))}
    </div>
  );
}
