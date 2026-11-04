"use client";

/** Everything that is not chat (WP13.1b). */

import {
  BookOpen,
  ChevronRight,
  CircleAlert,
  Database,
  LogOut,
  MessageSquareQuote,
  Moon,
  ScrollText,
  SlidersHorizontal,
  Sun,
  Users,
} from "lucide-react";
import { MotionConfig, motion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useState, type ReactNode } from "react";

import { ArchivedChats } from "@/components/screens/archived-chats";
import { Identity } from "@/components/screens/profile";
import { Badge, ROLE_TONES } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Stack } from "@/components/ui/page";
import { SkeletonList } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { createApi, type ActiveDataSource, type Me } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";
import { PALETTES, usePalette, useTheme, type Theme } from "@/lib/theme";
import { useOrgRole } from "@/lib/use-org-role";
import { cn } from "@/lib/utils";

/** What each role may do, in the terms of architecture 6.2. */
const ROLE_SUMMARY: Record<string, string> = {
  reader: "You can ask questions and see your own chats.",
  contributor: "You can ask questions, and add knowledge, definitions and verified queries.",
  admin: "You can ask questions, add knowledge, and manage data sources, members and spend.",
};

/** A label on the left and its value beside it; stacked on a phone. */
const row =
  "grid gap-x-8 gap-y-2 py-3.5 first:pt-0 last:pb-0 sm:grid-cols-[160px_minmax(0,1fr)]";

function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className={cn(row, "sm:items-baseline")}>
      <dt className="text-[13px] font-medium text-muted-foreground">{term}</dt>
      <dd className="m-0 min-w-0 text-[14px] text-text">{children}</dd>
    </div>
  );
}

function Setting({
  label,
  labelFor,
  hint,
  inline = false,
  children,
}: {
  label: string;
  /** The control the label names, so clicking the words works too. */
  labelFor?: string | undefined;
  hint?: string | undefined;
  /** A single small control, such as a switch, kept on the same line as its label. */
  inline?: boolean | undefined;
  children: ReactNode;
}) {
  return (
    <div
      className={
        inline
          ? "flex flex-wrap items-center justify-between gap-x-6 gap-y-3 py-3.5 first:pt-0 last:pb-0"
          : cn(row, "sm:items-center")
      }
    >
      <div className={cn("grid min-w-0 gap-0.5", inline && "flex-1 basis-[260px]")}>
        {labelFor ? (
          <label htmlFor={labelFor} className="text-[13.5px] font-medium text-text">
            {label}
          </label>
        ) : (
          <p className="text-[13.5px] font-medium text-text">{label}</p>
        )}
        {hint && <p className="text-[12.5px] leading-snug text-muted-foreground">{hint}</p>}
      </div>
      <div className={inline ? "shrink-0" : "min-w-0"}>{children}</div>
    </div>
  );
}

/** Somewhere to go from here. The whole tile is the link; its name is the title. */
function Destination({
  href,
  icon,
  title,
  children,
}: {
  href: string;
  icon: ReactNode;
  title: string;
  children: string;
}) {
  const description = useId();
  return (
    <Link
      href={href}
      aria-label={title}
      aria-describedby={description}
      className="group flex items-center gap-3 rounded-md border border-border bg-surface p-3 shadow-[0_1px_2px_rgba(var(--shadow-rgb),.04)] transition-[border-color,box-shadow,transform] hover:-translate-y-px hover:border-focus hover:shadow-[0_6px_16px_rgba(var(--shadow-rgb),.08)]"
    >
      <span
        aria-hidden="true"
        className="grid size-9 shrink-0 place-items-center rounded-sm bg-brand-soft text-brand-ink [&_svg]:size-[18px]"
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] font-medium text-text">{title}</span>
        <span id={description} className="block truncate text-[12.5px] text-muted-foreground">
          {children}
        </span>
      </span>
      <ChevronRight
        aria-hidden="true"
        className="size-4 shrink-0 text-faint transition-[color,transform] group-hover:translate-x-0.5 group-hover:text-brand-ink"
      />
    </Link>
  );
}

function PalettePicker() {
  const { palette, setPalette } = usePalette();
  return (
    <div
      role="group"
      aria-label="Palette"
      className="-ml-2.5 grid grid-cols-4 gap-y-2 sm:flex sm:flex-wrap"
    >
      {PALETTES.map((option) => {
        const on = option.key === palette;
        return (
          <button
            key={option.key}
            type="button"
            aria-pressed={on}
            onClick={() => setPalette(option.key)}
            className="group grid w-[60px] justify-items-center gap-1.5 rounded-md pt-1 pb-1.5 outline-none focus-visible:ring-[3px] focus-visible:ring-focus"
          >
            <span className="relative grid size-10 place-items-center">
              {on && (
                <motion.span
                  layoutId="palette-ring"
                  aria-hidden="true"
                  className="absolute inset-0 rounded-full ring-2 ring-brand"
                  transition={{ type: "spring", stiffness: 520, damping: 38 }}
                />
              )}
              <span
                aria-hidden="true"
                className="size-8 rounded-full shadow-[inset_0_0_0_1px_rgba(var(--shadow-rgb),.16)] transition-transform duration-200 group-hover:scale-110"
                style={{ background: `linear-gradient(135deg, ${option.accent} 50%, ${option.bg} 50%)` }}
              />
            </span>
            <span
              className={cn(
                "text-[12px] leading-none",
                on ? "font-semibold text-text" : "text-muted-foreground group-hover:text-text",
              )}
            >
              {option.name}
            </span>
          </button>
        );
      })}
    </div>
  );
}

const MODES: { value: Theme; label: string; icon: ReactNode }[] = [
  { value: "light", label: "Light", icon: <Sun /> },
  { value: "dark", label: "Dark", icon: <Moon /> },
];

function ModeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div
      role="group"
      aria-label="Mode"
      className="inline-flex rounded-full border border-border-soft bg-surface-2 p-1"
    >
      {MODES.map((mode) => {
        const on = theme === mode.value;
        return (
          <button
            key={mode.value}
            type="button"
            aria-pressed={on}
            onClick={() => setTheme(mode.value)}
            className={cn(
              "relative inline-flex h-8 items-center gap-1.5 rounded-full px-4 text-[13px] font-medium outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-focus [&_svg]:size-4",
              on ? "text-text" : "text-muted-foreground hover:text-text",
            )}
          >
            {on && (
              <motion.span
                layoutId="mode-thumb"
                aria-hidden="true"
                className="absolute inset-0 rounded-full bg-surface shadow-[0_1px_3px_rgba(var(--shadow-rgb),.14)]"
                transition={{ type: "spring", stiffness: 520, damping: 40 }}
              />
            )}
            <span aria-hidden="true" className="relative">
              {mode.icon}
            </span>
            <span className="relative">{mode.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/** A section that exists in the plan and not yet in the product. */
function ComingSoon({
  title,
  icon,
  children,
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  const heading = useId();
  return (
    <section
      aria-labelledby={heading}
      className="flex flex-col gap-3 rounded-lg border border-dashed border-border bg-surface/50 p-5"
    >
      <div className="flex items-center justify-between gap-3">
        <span
          aria-hidden="true"
          className="grid size-9 place-items-center rounded-md bg-surface-2 text-muted-foreground [&_svg]:size-[18px]"
        >
          {icon}
        </span>
        <Badge>Coming soon</Badge>
      </div>
      <div className="grid gap-1">
        <h3 id={heading} className="font-serif text-[16px] leading-snug font-semibold text-text">
          {title}
        </h3>
        <p className="text-[13px] leading-relaxed text-muted-foreground">{children}</p>
      </div>
    </section>
  );
}

function ErrorLine({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="flex items-start gap-2 text-[13px] text-bad-ink">
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <span className="min-w-0">{children}</span>
    </p>
  );
}

export function Settings({ orgId }: { orgId: string }) {
  const session = useSession();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);
  const { role } = useOrgRole(orgId);
  const costSwitch = useId();

  const [me, setMe] = useState<Me | null>(null);
  const [active, setActive] = useState<ActiveDataSource | null>(null);
  // : Null while unknown. The switch defaults to visible (D-066), so rendering.
  const [showCost, setShowCost] = useState<boolean | null>(null);
  const [savingCost, setSavingCost] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [costError, setCostError] = useState<string | null>(null);

  const isAdmin = role === "admin";
  const canWriteDefinitions = isAdmin || role === "contributor";

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const [who, chosen, spendVisible] = await Promise.all([
          api.me(),
          api.activeDataSource(orgId),
          api.showRunCost(orgId),
        ]);
        if (!alive) return;
        setMe(who);
        setActive(chosen);
        setShowCost(spendVisible);
      } catch (cause) {
        if (alive) setLoadError(cause instanceof Error ? cause.message : "Settings could not load.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, orgId]);

  const loading = me === null && loadError === null;
  const membership = me?.memberships.find((entry) => entry.org_id === orgId) ?? null;

  const toggleCost = useCallback(async () => {
    if (showCost === null) return;
    setSavingCost(true);
    setCostError(null);
    try {
      setShowCost(await api.setShowRunCost(orgId, !showCost));
    } catch (cause) {
      setCostError(cause instanceof Error ? cause.message : "That could not be saved.");
    } finally {
      setSavingCost(false);
    }
  }, [api, orgId, showCost]);

  const costState =
    showCost === null ? "—" : showCost ? "Shown to everyone" : "Hidden from everyone";

  return (
    <Stack>
      {loadError && <ErrorLine>{loadError}</ErrorLine>}

      <Card
        title="You"
        action={
          <Button size="sm" onClick={() => void session.signOut()}>
            <LogOut aria-hidden="true" />
            Sign out
          </Button>
        }
      >
        {me ? (
          <Identity me={me} />
        ) : loading ? (
          <SkeletonList rows={2} avatar label="Loading settings" />
        ) : (
          <p className="text-[14px] text-muted-foreground">—</p>
        )}
      </Card>

      <Card title="Organization" subtitle="What this organization is, and what it answers from.">
        {loading ? (
          <SkeletonList rows={3} label="Loading your organization" />
        ) : (
          <dl className="divide-y divide-border-soft">
            <Fact term="Name">{membership?.org_name ?? "—"}</Fact>
            <Fact term="Your role">
              {membership ? (
                <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <Badge tone={ROLE_TONES[membership.role] ?? "neutral"} className="capitalize">
                    {membership.role}
                  </Badge>
                  {ROLE_SUMMARY[membership.role] && (
                    <span className="text-[13px] text-muted-foreground">
                      {ROLE_SUMMARY[membership.role]}
                    </span>
                  )}
                </span>
              ) : (
                "—"
              )}
            </Fact>
            <Fact term="Answers from">
              {active === null ? (
                "—"
              ) : active.data_source_name ? (
                <span className="inline-flex min-w-0 items-center gap-2">
                  <Database aria-hidden="true" className="size-4 shrink-0 text-brand-ink" />
                  <span className="truncate font-medium">{active.data_source_name}</span>
                </span>
              ) : (
                <span className="text-muted-foreground">
                  {isAdmin
                    ? "No database chosen yet — choose one under Data sources."
                    : "No database chosen yet. An Admin can choose one."}
                </span>
              )}
            </Fact>
          </dl>
        )}

        {/* Every destination gates itself; these links decide what to render. */}
        <div className="mt-5 grid gap-2.5 border-t border-border-soft pt-5 sm:grid-cols-3">
          <Destination href={`/orgs/${orgId}/settings/members`} icon={<Users />} title="Members">
            People and their roles
          </Destination>
          {isAdmin && (
            <Destination href={`/orgs/${orgId}/data-sources`} icon={<Database />} title="Data sources">
              Read-only databases
            </Destination>
          )}
          {canWriteDefinitions && (
            <Destination href={`/orgs/${orgId}/documents`} icon={<BookOpen />} title="Knowledge">
              What it reads first
            </Destination>
          )}
        </div>
      </Card>

      {/* *D-066.** Not a permission — off hides spend from everyone, Admins included. */}
      <Card
        title="Spend"
        subtitle="Whether every answer shows what it cost and how many tokens it used."
      >
        {isAdmin ? (
          <Setting
            label="Show cost on answers"
            labelFor={costSwitch}
            hint="Off hides it from everyone, Admins included."
            inline
          >
            <div className="flex items-center gap-3">
              <span className="text-[13px] text-muted-foreground" aria-live="polite">
                {savingCost ? "Saving…" : costState}
              </span>
              {showCost !== null && (
                <Switch
                  id={costSwitch}
                  checked={showCost}
                  disabled={savingCost}
                  onCheckedChange={() => void toggleCost()}
                  className="data-[state=unchecked]:bg-faint"
                />
              )}
            </div>
          </Setting>
        ) : (
          <Setting label="Cost on answers" hint="An Admin can change this." inline>
            {showCost === null ? (
              <span className="text-[13px] text-muted-foreground">—</span>
            ) : (
              <Badge tone={showCost ? "mint" : "neutral"}>{costState}</Badge>
            )}
          </Setting>
        )}
        {costError && (
          <div className="mt-3">
            <ErrorLine>{costError}</ErrorLine>
          </div>
        )}
      </Card>

      <Card
        title="Appearance"
        subtitle="Sage on light is the default. Your choice is kept in this browser."
      >
        <MotionConfig reducedMotion="user">
          <div className="divide-y divide-border-soft">
            <Setting label="Palette">
              <PalettePicker />
            </Setting>
            <Setting label="Mode">
              <ModeToggle />
            </Setting>
          </div>
        </MotionConfig>
      </Card>

      <ArchivedChats orgId={orgId} />

      <section aria-labelledby="settings-coming-next" className="mt-3 grid gap-3">
        <h2 id="settings-coming-next" className="px-1 text-[13px] font-medium text-muted-foreground">
          Coming next
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          <ComingSoon title="System instructions" icon={<ScrollText />}>
            Standing guidance every question in this organization is answered with — house
            definitions, what to avoid, which figures matter. Not built yet, so nothing here is
            being sent to the model.
          </ComingSoon>

          <ComingSoon title="Tone" icon={<MessageSquareQuote />}>
            How an answer is written: brief or thorough, plain or technical. Not built yet — answers
            are composed the one way today.
          </ComingSoon>

          <ComingSoon title="Preferences" icon={<SlidersHorizontal />}>
            Per-person settings such as a default currency and date format. Not built yet.
          </ComingSoon>
        </div>
      </section>
    </Stack>
  );
}
