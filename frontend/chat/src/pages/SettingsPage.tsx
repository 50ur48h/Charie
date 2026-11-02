import { useState } from "react";
import { useNavigate } from "react-router";
import { Check, Database, Layers } from "lucide-react";
import {
  Button,
  Card,
  ConfirmDialog,
  formatDataThrough,
  formatDate,
  IconBox,
  isThemeKey,
  Page,
  PageHeader,
  Pill,
  setTheme,
  Slider,
  Switch,
  toast,
  useClearMemories,
  useDeleteMemory,
  useLogout,
  useMe,
  useMemories,
  useSettings,
  useStatus,
  useUpdateSettings,
  THEMES,
  type Settings,
  type ThemeKey,
} from "@charie/shared";
import { ChangePasswordDialog } from "./ChangePasswordDialog";
import { MemorySection } from "./MemorySection";

// Preview swatches for the six approved themes (Calm settings design).
const PALETTES: Record<ThemeKey, { bg: string; side: string; accent: string; bubble: string; soft: string }> = {
  sage: { bg: "#F4F6F1", side: "#EBEFE7", accent: "#6E9277", bubble: "#E3E9DE", soft: "#B5CDB9" },
  lavender: { bg: "#F6F5FA", side: "#EEECF6", accent: "#8A7FC4", bubble: "#E8E5F3", soft: "#C6BFEA" },
  mist: { bg: "#F3F6F9", side: "#E9EEF4", accent: "#6286B0", bubble: "#E2E9F2", soft: "#B3C8E2" },
  seafoam: { bg: "#F2F7F6", side: "#E7F0EE", accent: "#5A9E96", bubble: "#E0ECE9", soft: "#ACD6D0" },
  mauve: { bg: "#F9F5F6", side: "#F2EBED", accent: "#A97887", bubble: "#EFE4E8", soft: "#CFC0D3" },
  slate: { bg: "#F5F5F4", side: "#ECECEA", accent: "#5F6B7A", bubble: "#E6E6E3", soft: "#BCC4CE" },
};

function SettingRow({
  title,
  body,
  control,
  label,
}: {
  title: string;
  body: string;
  control: React.ReactNode;
  label: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-[18px] gap-y-3 border-t border-border-soft py-4 first:border-t-0 first:pt-0 last:pb-0">
      <div className="min-w-[220px] flex-1">
        <div className="text-[14.5px] font-semibold">{title}</div>
        <div id={label} className="mt-0.5 text-[13px] text-muted">
          {body}
        </div>
      </div>
      {control}
    </div>
  );
}

function Segmented<T extends string>({
  label,
  options,
  value,
  onPick,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onPick: (next: T) => void;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex flex-wrap gap-1 rounded-[12px] bg-surface-2 p-1"
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onPick(option.value)}
            className={`inline-flex h-8 items-center whitespace-nowrap rounded-[9px] px-[14px] text-[13.5px] font-medium not-disabled:hover:text-text disabled:cursor-not-allowed disabled:opacity-50 ${
              selected ? "bg-surface text-text shadow-tab" : "text-muted"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function ThemeCards({
  current,
  onPick,
}: {
  current: ThemeKey;
  onPick: (key: ThemeKey) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" role="group" aria-label="Color theme">
      {THEMES.map((theme) => {
        const palette = PALETTES[theme.key];
        const selected = theme.key === current;
        return (
          <button
            key={theme.key}
            type="button"
            aria-pressed={selected}
                        onClick={() => onPick(theme.key)}
            className={`rounded-[16px] border-[1.5px] bg-surface p-2 text-left transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-0.5 data-[pressed=true]:shadow-pop ${
              selected ? "border-accent shadow-pop" : "border-border"
            }`}
            data-pressed={selected}
          >
            <span
              className="flex h-[72px] overflow-hidden rounded-[10px]"
              style={{ background: palette.bg }}
              aria-hidden="true"
            >
              <span className="grid w-[32%] content-start gap-[5px] p-[8px_6px]" style={{ background: palette.side }}>
                <i className="mb-[3px] block size-[12px] rounded-[4px]" style={{ background: palette.accent }} />
                <b className="block h-[5px] rounded-[3px] bg-[rgba(0,0,0,.08)]" />
                <b className="block h-[5px] rounded-[3px] bg-[rgba(0,0,0,.08)]" />
              </span>
              <span className="grid flex-1 content-start gap-[6px] p-2.5">
                <span className="h-[12px] w-[46%] justify-self-end rounded-[6px]" style={{ background: palette.bubble }} />
                <span className="h-[6px] rounded-[3px] bg-[rgba(0,0,0,.1)]" />
                <span className="h-[6px] w-[60%] rounded-[3px] bg-[rgba(0,0,0,.1)]" />
              </span>
            </span>
            <span className="flex items-center gap-2 px-1 pb-0.5 pt-2 text-[14px] font-semibold">
              {theme.name}
              {theme.key === "sage" && (
                <em className="rounded-full bg-accent-soft px-[7px] py-px text-[11.5px] font-semibold not-italic text-accent-ink">
                  Default
                </em>
              )}
              {selected && <Check aria-hidden="true" className="ml-auto text-accent [--icon:16px]" />}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function SettingsPage() {
  const navigate = useNavigate();
  const settings = useSettings();
  const update = useUpdateSettings();
  const me = useMe();
  const status = useStatus();
  const statusData = status.data?.data ?? null;
  const statusKnowledge = status.data?.knowledge ?? null;
  const dataConnected = statusData?.status === "connected";
  const dataTitle = statusData
    ? `${statusData.name} · ${statusData.kind === "postgres" ? "Postgres" : statusData.kind} · read-only${statusData.data_through ? ` · data up to ${formatDate(statusData.data_through.slice(0, 10))}` : ""}`
    : "No database connected";
  const knowledgeVersion = statusKnowledge?.version ?? null;
  const knowledgeTitle =
    knowledgeVersion !== null ? `Knowledge version ${knowledgeVersion}` : "No knowledge published yet";
  const knowledgeEntries = statusKnowledge?.entries ?? 0;
  const knowledgeDocuments = statusKnowledge?.documents ?? 0;
  const knowledgeSub =
    knowledgeVersion !== null
      ? `${knowledgeEntries} ${knowledgeEntries === 1 ? "entry" : "entries"} · ${knowledgeDocuments} ${knowledgeDocuments === 1 ? "document" : "documents"}${statusKnowledge?.published_at ? ` · updated ${formatDataThrough(statusKnowledge.published_at)}` : ""}`
      : "Publish the first version in the Learner.";
  const learnerUrl = status.data?.learner_url ?? me.data?.learner_url ?? null;
  const memories = useMemories();
  const removeMemory = useDeleteMemory();
  const clearMemories = useClearMemories();
  const logout = useLogout();

  const [minutes, setMinutes] = useState<number | null>(null);
  const [forgetId, setForgetId] = useState<number | null>(null);
  const [forgetAll, setForgetAll] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [signoutError, setSignoutError] = useState<string | null>(null);

  const data: Settings | undefined = settings.data;
  const activeTheme: ThemeKey =
    data && isThemeKey(data.theme) ? data.theme : "sage";

  function save(patch: Partial<Settings>, revert: () => void): void {
    update.mutate(patch, {
      onError: (error) => {
        revert();
        toast(error.message);
      },
    });
  }

  function pickTheme(key: ThemeKey): void {
    if (!data || key === data.theme) return;
    const previous = activeTheme;
    setTheme(key);
    save({ theme: key }, () => setTheme(previous));
  }

  if (settings.isError) {
    return (
      <Page narrow>
        <PageHeader
          title="Settings"
          lead="Make Charie look and answer the way you like."
        />
        <Card padded role="alert">
          <p className="text-[14px]">Couldn&apos;t load your settings.</p>
          <Button variant="ghost" className="mt-2" onClick={() => void settings.refetch()}>
            Try again
          </Button>
        </Card>
      </Page>
    );
  }

  return (
    <Page narrow>
      <PageHeader
        title="Settings"
        lead="Make Charie look and answer the way you like."
      />
      {!data ? (
        <Card padded>
          <p className="text-[14px] text-muted" role="status">
            Loading settings…
          </p>
        </Card>
      ) : (
        <div className="grid gap-[18px]">
          <section aria-label="Appearance">
            <Card padded>
              <h2 className="card-title">Color theme</h2>
              <p className="card-sub">Soft colors only. Pick one and the whole app changes right away.</p>
              <div className="mt-3.5">
                <ThemeCards current={activeTheme} onPick={pickTheme} />
              </div>
            </Card>
          </section>

          <section aria-label="Answers">
            <Card padded>
              <h2 className="card-title">Answers</h2>
              <div className="mt-1">
                <SettingRow
                  title="Thinking time limit"
                  body="When time runs out, Charie writes the best answer it has and says what's still unknown."
                  label="thinking-desc"
                  control={
                    <div className="w-[260px] min-w-0">
                      <div className="mb-1 text-right font-serif text-[18px] font-semibold" aria-live="polite">
                        {minutes ?? data.thinking_minutes} minutes
                      </div>
                      <Slider
                        aria-label="Thinking time limit"
                        min={2}
                        max={15}
                        step={1}
                        value={minutes ?? data.thinking_minutes}
                        onValueChange={(next) => {
                          setMinutes(next);
                          save({ thinking_minutes: next }, () => setMinutes(data.thinking_minutes));
                        }}
                      />
                    </div>
                  }
                />
                <SettingRow
                  title="Answer length"
                  body="How much detail Charie gives by default."
                  label="length-desc"
                  control={
                    <Segmented
                      label="Answer length"
                      options={[
                        { value: "short", label: "Short" },
                        { value: "normal", label: "Normal" },
                        { value: "detailed", label: "Detailed" },
                      ]}
                      value={data.answer_length}
                      onPick={(next) => save({ answer_length: next }, () => {})}
                    />
                  }
                />
                <SettingRow
                  title="Number format"
                  body="How money and big numbers are shown."
                  label="format-desc"
                  control={
                    <Segmented
                      label="Number format"
                      options={[
                        { value: "short", label: "$1.42M" },
                        { value: "full", label: "$1,420,000" },
                      ]}
                      value={data.number_format}
                      onPick={(next) => save({ number_format: next }, () => {})}
                    />
                  }
                />
                <SettingRow
                  title="Show “I read this as…”"
                  body="Charie starts vague questions by saying how it understood them."
                  label="reading-desc"
                  control={
                    <Switch
                      aria-label="Show I read this as"
                      checked={data.show_reading}
                      onCheckedChange={(next) => save({ show_reading: next }, () => {})}
                    />
                  }
                />
              </div>
            </Card>
          </section>

          <section aria-label="Memory">
            <Card padded>
              <h2 className="card-title">Memory</h2>
              <SettingRow
                title="Remember things I tell Charie"
                body="Charie keeps your preferences across chats. Only you can see them."
                label="memory-desc"
                control={
                  <Switch
                    aria-label="Remember things I tell Charie"
                    checked={data.memory_on}
                    onCheckedChange={(next) => save({ memory_on: next }, () => {})}
                  />
                }
              />
              <MemorySection
                memories={memories.data}
                isError={memories.isError}
                onRetry={() => void memories.refetch()}
                memoryOn={data.memory_on}
                onForget={(id) => setForgetId(id)}
                onForgetAll={() => setForgetAll(true)}
                forgetting={removeMemory.isPending}
                forgettingAll={clearMemories.isPending}
              />
            </Card>
          </section>

          <section aria-label="Data">
            <Card padded>
              <h2 className="card-title">Data</h2>
              <p className="card-sub">What Charie is connected to. The Learner manages these.</p>
              <div className="mt-3 grid gap-2">
                <div className="flex items-center gap-3.5 rounded-[14px] bg-surface-2 p-[14px_16px]">
                  <IconBox icon={Database} tone="good" />
                  <div className="min-w-0">
                    <div className="text-[14px] font-semibold">{dataTitle}</div>
                    {!statusData && (
                      <div className="text-[12.5px] text-muted">Connect one in the Learner.</div>
                    )}
                  </div>
                  <Pill
                    tone={dataConnected ? "good" : statusData ? "bad" : "neutral"}
                    className="ml-auto flex-none"
                  >
                    {dataConnected ? "Connected" : statusData ? "Connection problem" : "Not connected"}
                  </Pill>
                </div>
                <div className="flex items-center gap-3.5 rounded-[14px] bg-surface-2 p-[14px_16px]">
                  <IconBox icon={Layers} />
                  <div className="min-w-0">
                    <div className="text-[14px] font-semibold">{knowledgeTitle}</div>
                    <div className="text-[12.5px] text-muted">{knowledgeSub}</div>
                  </div>
                  {learnerUrl && (
                    <Button variant="outline" size="sm" className="ml-auto flex-none" asChild>
                      <a href={learnerUrl} target="_blank" rel="noreferrer">
                        Open Learner
                      </a>
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          </section>

          <section aria-label="Account">
            <Card padded>
              <h2 className="card-title">Account</h2>
              <div className="mt-1">
                <SettingRow
                  title="Password"
                  body="One shared password for Charie."
                  label="password-desc"
                  control={
                    <Button variant="outline" size="sm" onClick={() => setChangingPassword(true)}>
                      Change password
                    </Button>
                  }
                />
                <SettingRow
                  title="Sign out"
                  body="You'll need the password to come back."
                  label="signout-desc"
                  control={
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={logout.isPending}
                      onClick={() => {
                        setSignoutError(null);
                        logout.mutate(undefined, {
                          onSuccess: () => navigate("/login"),
                          onError: () => setSignoutError("Couldn't sign out. Try again."),
                        });
                      }}
                    >
                      {logout.isPending ? "Signing out…" : "Sign out"}
                    </Button>
                  }
                />
              </div>
              {signoutError && (
                <p role="alert" className="mt-2 text-[13px] text-bad-ink">
                  {signoutError}
                </p>
              )}
            </Card>
          </section>
        </div>
      )}

      <ConfirmDialog
        open={forgetId !== null}
        onOpenChange={(open) => !open && setForgetId(null)}
        title="Forget this?"
        body="Charie won't use this anymore."
        confirmLabel={removeMemory.isPending ? "Forgetting…" : "Forget"}
        tone="danger"
        onConfirm={() => {
          if (forgetId !== null) {
            removeMemory.mutate(forgetId, {
              onSuccess: () => toast("Forgotten. Charie won't use this anymore."),
            });
          }
        }}
      />
      <ConfirmDialog
        open={forgetAll}
        onOpenChange={setForgetAll}
        title="Forget everything?"
        body="Charie forgets every preference you told it. This can't be undone."
        confirmLabel={clearMemories.isPending ? "Forgetting…" : "Forget everything"}
        tone="danger"
        onConfirm={() => clearMemories.mutate()}
      />
      {changingPassword && <ChangePasswordDialog onClose={() => setChangingPassword(false)} />}
    </Page>
  );
}
