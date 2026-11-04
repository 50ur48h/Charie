"use client";

/** Who belongs to this organization, and what each person may do (WP13.1b). */

import {
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Copy,
  KeyRound,
  Send,
  TriangleAlert,
} from "lucide-react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { initials } from "@/components/shell/sidebar";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge, ROLE_TONES } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, controlClass } from "@/components/ui/input";
import { Stack } from "@/components/ui/page";
import { SkeletonList } from "@/components/ui/skeleton";
import {
  createApi,
  type ArmedRecoveryGrant,
  type Invitation,
  type Member,
  type RecoveryGrant,
} from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";
import { personLabel } from "@/lib/identity";
import { cn } from "@/lib/utils";

const ROLES = ["reader", "contributor", "admin"] as const;

/** What each role may do, in the terms of architecture 6.2. */
const ROLE_SUMMARY: Record<string, string> = {
  reader: "Readers ask questions and see their own chats.",
  contributor: "Contributors can also add knowledge, definitions and verified queries.",
  admin: "Admins can also manage data sources, members and spend.",
};

function roleName(role: string): string {
  return role.charAt(0).toUpperCase() + role.slice(1);
}

function withArticle(role: string): string {
  return /^[aeiou]/i.test(role) ? `an ${role}` : `a ${role}`;
}

const day = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });

function formatDay(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : day.format(at);
}

/** A member whose token carried no email claim still has to be identifiable. */
function who(member: Member): { primary: string; secondary: string | null } {
  const name = member.name?.trim();
  return {
    primary: name || personLabel(member, member.user_id),
    secondary: name && member.email ? member.email : null,
  };
}

/** A native select, so every device opens its own picker. */
function RoleSelect({
  id,
  label,
  value,
  disabled = false,
  compact = false,
  onChange,
}: {
  id?: string | undefined;
  /** The accessible name, when no visible label points at this select. */
  label?: string | undefined;
  value: string;
  disabled?: boolean | undefined;
  compact?: boolean | undefined;
  onChange: (role: string) => void;
}) {
  // A role this screen does not know is still shown as itself.
  const options: readonly string[] = (ROLES as readonly string[]).includes(value)
    ? ROLES
    : [value, ...ROLES];
  return (
    <div className="relative">
      <select
        id={id}
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          controlClass,
          "cursor-pointer appearance-none pr-9",
          compact && "h-8 w-[136px] rounded-sm pr-8 pl-2.5 text-[13px]",
        )}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {roleName(option)}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute top-1/2 -translate-y-1/2 text-muted-foreground",
          compact ? "right-2.5 size-3.5" : "right-3 size-4",
        )}
      />
    </div>
  );
}

function ErrorLine({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="mt-3 flex items-start gap-2 text-[13px] text-bad-ink">
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <span className="min-w-0">{children}</span>
    </p>
  );
}

/** A secret shown once: selectable in full, with a button that copies it. */
function OneTimeSecret({
  value,
  label,
  copyLabel,
  copied,
}: {
  value: string;
  label: string;
  copyLabel: string;
  copied: string;
}) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      toast(copied);
    } catch {
      toast("Could not copy. Select the text and copy it yourself.");
    }
  };
  return (
    <div className="flex items-center gap-2 rounded-sm border border-border bg-surface p-1 pl-3">
      <input
        readOnly
        aria-label={label}
        value={value}
        onFocus={(event) => event.currentTarget.select()}
        className="min-w-0 flex-1 bg-transparent font-mono text-[12.5px] text-text outline-none"
      />
      <Button size="sm" onClick={() => void copy()}>
        <Copy aria-hidden="true" />
        {copyLabel}
      </Button>
    </div>
  );
}

function IssuedLink({ invitation }: { invitation: Invitation }) {
  // Computed during render, not in an effect.
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const link = `${origin}/invitations/accept?token=${encodeURIComponent(invitation.token)}`;

  return (
    <div className="mt-4 grid animate-fade-up gap-3 rounded-md bg-good-soft p-4">
      <p className="flex items-start gap-2 text-[13.5px] leading-relaxed text-good-ink">
        <CircleCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        <span>
          Invitation for <strong className="font-semibold">{invitation.email}</strong> as{" "}
          {invitation.role}. Send them this link — the token is stored only as a hash, so it
          cannot be shown again.
        </span>
      </p>
      <OneTimeSecret value={link} label="Invitation link" copyLabel="Copy link" copied="Link copied" />
      <p className="text-[12.5px] text-good-ink">Expires {formatDay(invitation.expires_at)}.</p>
    </div>
  );
}

/** What a grant's line says beneath its label: when it ends, or when it ended. */
function grantDetail(grant: RecoveryGrant): string {
  if (grant.state === "used" && grant.used_at) return `Used ${formatDay(grant.used_at)}`;
  if (grant.state === "revoked" && grant.revoked_at) return `Revoked ${formatDay(grant.revoked_at)}`;
  if (grant.state === "expired") return `Expired ${formatDay(grant.expires_at)}`;
  return `Valid until ${formatDay(grant.expires_at)}`;
}

type Ask =
  | { kind: "role"; member: Member; role: string }
  | { kind: "remove"; member: Member }
  | { kind: "revoke"; grant: RecoveryGrant };

type Where = "members" | "invite" | "recovery";

export function Members({ orgId, role: myRole }: { orgId: string; role: string | null }) {
  const session = useSession();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);
  const inviteRole = useId();

  // B-008: a Reader was shown Change role, Remove and Send invite, earned a 403 from each.
  const isAdmin = myRole === "admin";

  const [members, setMembers] = useState<Member[] | null>(null);
  // : Which row is the person looking at this, so it can say "You" and so the.
  const [myId, setMyId] = useState<string | null>(null);
  const [error, setError] = useState<{ where: Where; message: string } | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<string>("reader");
  const [issued, setIssued] = useState<Invitation | null>(null);
  const [busy, setBusy] = useState(false);
  // : B-017. Null while loading, so an empty panel is never mistaken for.
  const [grants, setGrants] = useState<RecoveryGrant[] | null>(null);
  const [grantLabel, setGrantLabel] = useState("");
  // : Shown exactly once, in the response to arming.
  const [armed, setArmed] = useState<ArmedRecoveryGrant | null>(null);
  // : The question being asked. Kept after the dialog closes, so its words do.
  const [ask, setAsk] = useState<Ask | null>(null);
  const [asking, setAsking] = useState(false);
  const returnFocus = useRef<HTMLElement | null>(null);
  const peopleList = useRef<HTMLUListElement>(null);
  const grantList = useRef<HTMLUListElement>(null);

  const load = useCallback(async () => {
    try {
      setMembers(await api.members(orgId));
    } catch (cause) {
      setError({
        where: "members",
        message: cause instanceof Error ? cause.message : "Could not load members",
      });
    }
  }, [api, orgId]);

  useEffect(() => {
    // Guarded so a slow response cannot write into an unmounted screen.
    let active = true;
    void (async () => {
      try {
        const next = await api.members(orgId);
        if (active) setMembers(next);
      } catch (cause) {
        if (active) {
          setError({
            where: "members",
            message: cause instanceof Error ? cause.message : "Could not load",
          });
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [api, orgId]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const me = await api.me();
        if (active) setMyId(me.user_id);
      } catch {
        // Only the "You" marker depends on this; the list is right without it.
      }
    })();
    return () => {
      active = false;
    };
  }, [api]);

  // B-017. Loaded only for an Admin, because only an Admin may list them.
  useEffect(() => {
    if (!isAdmin) return;
    let active = true;
    void (async () => {
      try {
        const next = await api.recoveryGrants(orgId);
        if (active) setGrants(next);
      } catch {
        // Left null: the members list is the point of this screen.
        if (active) setGrants([]);
      }
    })();
    return () => {
      active = false;
    };
  }, [api, orgId, isAdmin]);

  const run = async (where: Where, action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (cause) {
      // The API's own words: "Your role does not permit this action" and "This is the only...
      setError({ where, message: cause instanceof Error ? cause.message : "That did not work" });
    } finally {
      setBusy(false);
    }
  };

  const askFirst = (next: Ask) => {
    // The dialog has no trigger of its own.
    returnFocus.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setAsk(next);
    setAsking(true);
  };

  const confirm = () => {
    // A second click while the dialog fades out must not send the request again.
    if (!ask || busy) return;
    if (ask.kind === "role") {
      const { member, role: next } = ask;
      void run("members", async () => {
        await api.changeRole(orgId, member.user_id, next);
        toast(`${who(member).primary} is now ${withArticle(next)}`);
      });
    } else if (ask.kind === "remove") {
      const { member } = ask;
      // The row, and the button that opened this, are about to go.
      returnFocus.current = peopleList.current;
      void run("members", async () => {
        await api.removeMember(orgId, member.user_id);
        toast(`Removed ${who(member).primary}`);
      });
    } else {
      const { grant } = ask;
      // A revoked grant has no Revoke button to come back to.
      returnFocus.current = grantList.current;
      void run("recovery", async () => {
        await api.revokeRecoveryGrant(orgId, grant.id);
        setGrants(await api.recoveryGrants(orgId));
        if (armed?.id === grant.id) setArmed(null);
        toast(`Revoked “${grant.label}”`);
      });
    }
  };

  const errorFor = (where: Where) =>
    error?.where === where ? <ErrorLine>{error.message}</ErrorLine> : null;

  return (
    <Stack>
      <Card
        title="People"
        subtitle={isAdmin ? undefined : "Only an Admin can change roles or invite people."}
        action={
          members ? <Badge className="tabular-nums">{members.length}</Badge> : undefined
        }
      >
        {members === null && error?.where !== "members" && (
          <SkeletonList rows={3} avatar label="Loading members" />
        )}
        {members && (
          <MotionConfig reducedMotion="user">
            <ul
              ref={peopleList}
              tabIndex={-1}
              aria-label="People in this organization"
              className="-my-1 rounded-md outline-offset-4"
            >
              <AnimatePresence initial={false}>
                {members.map((member, index) => {
                  const { primary, secondary } = who(member);
                  const isYou = member.user_id === myId;
                  return (
                    <motion.li
                      key={member.user_id}
                      layout
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0, transition: { delay: index * 0.03 } }}
                      exit={{ opacity: 0, transition: { duration: 0.15 } }}
                      className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border-soft py-3 last:border-b-0"
                    >
                      <div className="flex min-w-0 flex-1 basis-[220px] items-center gap-3">
                        <span
                          aria-hidden="true"
                          className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-soft text-[13px] font-semibold text-brand-ink"
                        >
                          {initials(member, member.user_id)}
                        </span>
                        <div className="min-w-0">
                          <p className="flex min-w-0 items-center gap-2">
                            <span className="truncate text-[14px] font-medium text-text">
                              {primary}
                            </span>
                            {isYou && <Badge>You</Badge>}
                          </p>
                          {secondary && (
                            <p className="truncate text-[12.5px] text-muted-foreground">
                              {secondary}
                            </p>
                          )}
                        </div>
                      </div>
                      {isAdmin ? (
                        <div className="flex items-center gap-1 max-sm:w-full max-sm:pl-12">
                          <RoleSelect
                            label="Change role"
                            value={member.role}
                            disabled={busy}
                            compact
                            onChange={(next) => {
                              if (next !== member.role) askFirst({ kind: "role", member, role: next });
                            }}
                          />
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            onClick={() => askFirst({ kind: "remove", member })}
                            className="hover:bg-bad-soft hover:text-bad-ink"
                          >
                            Remove
                          </Button>
                        </div>
                      ) : (
                        <Badge tone={ROLE_TONES[member.role] ?? "neutral"} className="capitalize">
                          {member.role}
                        </Badge>
                      )}
                    </motion.li>
                  );
                })}
              </AnimatePresence>
            </ul>
          </MotionConfig>
        )}
        {errorFor("members")}
      </Card>

      {isAdmin && (
        <Card title="Invite someone" subtitle="Admins only. The link is shown once.">
          <form
            className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px_auto] sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              void run("invite", async () => {
                setIssued(await api.invite(orgId, email.trim(), role));
                setEmail("");
              });
            }}
          >
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="bob@example.com"
              autoComplete="off"
            />
            <div className="grid gap-1.5">
              <label className="text-[13px] font-medium text-text-2" htmlFor={inviteRole}>
                Role
              </label>
              <RoleSelect id={inviteRole} value={role} onChange={setRole} />
            </div>
            <Button variant="primary" size="lg" type="submit" disabled={busy || !email.trim()}>
              <Send aria-hidden="true" />
              {busy ? "Inviting…" : "Send invite"}
            </Button>
          </form>
          {ROLE_SUMMARY[role] && (
            <p className="mt-2.5 text-[12.5px] text-muted-foreground">{ROLE_SUMMARY[role]}</p>
          )}
          {errorFor("invite")}

          {issued && <IssuedLink key={issued.invitation_id} invitation={issued} />}
        </Card>
      )}

      {isAdmin && (
        <Card
          title="If nobody can sign in"
          subtitle="Admins only. A way back into this organization, armed in advance."
        >
          {/* *B-017.** Roles change through an Admin-only route. */}
          <p className="max-w-[68ch] text-[13.5px] leading-relaxed text-text-2">
            Arming a grant gives you a token to keep somewhere outside this product — a password
            manager, not an inbox. If every Admin here ever loses access, whoever holds it can
            claim Admin of this organization. It is shown once, can be used once, and you can
            revoke it at any time.
          </p>
          <form
            className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              void run("recovery", async () => {
                setArmed(await api.armRecoveryGrant(orgId, grantLabel.trim()));
                setGrantLabel("");
                setGrants(await api.recoveryGrants(orgId));
              });
            }}
          >
            <Input
              label="What it is for"
              value={grantLabel}
              onChange={(event) => setGrantLabel(event.target.value)}
              placeholder="Ops password manager"
            />
            <Button size="lg" type="submit" disabled={busy}>
              <KeyRound aria-hidden="true" />
              {busy ? "Arming…" : "Arm a recovery grant"}
            </Button>
          </form>
          {errorFor("recovery")}

          {armed && (
            <div className="mt-4 grid animate-fade-up gap-3 rounded-md bg-warn-soft p-4">
              <p className="flex items-start gap-2 text-[13.5px] leading-relaxed text-warn-ink">
                <KeyRound aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                <span>
                  Recovery token for “{armed.label}”, valid until {formatDay(armed.expires_at)}.
                  Copy it now — only its hash is stored, so it cannot be shown again.
                </span>
              </p>
              <OneTimeSecret
                value={armed.token}
                label="Recovery token"
                copyLabel="Copy token"
                copied="Token copied"
              />
            </div>
          )}

          <div className="mt-5 border-t border-border-soft pt-4">
            {grants === null ? (
              <SkeletonList rows={2} label="Loading recovery grants" />
            ) : grants.length === 0 ? (
              <p className="flex items-start gap-2 rounded-md bg-warn-soft px-3.5 py-3 text-[13px] leading-relaxed text-warn-ink">
                <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                <span>
                  Nothing armed. This organization has no way back if its Admins lose access.
                </span>
              </p>
            ) : (
              <ul
                ref={grantList}
                tabIndex={-1}
                aria-label="Recovery grants"
                className="-my-1 rounded-md outline-offset-4"
              >
                {grants.map((grant) => (
                  <li
                    key={grant.id}
                    className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border-soft py-3 last:border-b-0"
                  >
                    <div className="flex min-w-0 flex-1 basis-[220px] items-center gap-3">
                      <span
                        aria-hidden="true"
                        className="grid size-9 shrink-0 place-items-center rounded-md bg-surface-2 text-muted-foreground [&_svg]:size-4"
                      >
                        <KeyRound />
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-[14px] font-medium text-text">{grant.label}</p>
                        <p className="text-[12.5px] text-muted-foreground">{grantDetail(grant)}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 max-sm:pl-12">
                      <Badge tone={grant.state === "armed" ? "mint" : "neutral"} className="capitalize">
                        {grant.state}
                      </Badge>
                      {grant.state === "armed" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => askFirst({ kind: "revoke", grant })}
                          className="hover:bg-bad-soft hover:text-bad-ink"
                        >
                          Revoke
                        </Button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      )}

      <AlertDialog open={asking} onOpenChange={setAsking}>
        <AlertDialogContent
          className="gap-5 border-border bg-surface sm:max-w-[440px]"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (returnFocus.current?.isConnected) returnFocus.current.focus();
          }}
        >
          {ask && <Question ask={ask} myId={myId} />}
          <AlertDialogFooter>
            <AlertDialogCancel variant="secondary">Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant={ask?.kind === "role" ? "primary" : "danger"}
              disabled={busy}
              onClick={confirm}
            >
              {ask?.kind === "role" ? "Change role" : ask?.kind === "revoke" ? "Revoke" : "Remove"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Stack>
  );
}

/** The words of a confirmation: what will happen, and to whom. */
function Question({ ask, myId }: { ask: Ask; myId: string | null }) {
  let title: string;
  let body: string;
  if (ask.kind === "role") {
    const self = ask.member.user_id === myId;
    title = self
      ? `Make yourself ${withArticle(ask.role)}?`
      : `Make ${who(ask.member).primary} ${withArticle(ask.role)}?`;
    body = `${ROLE_SUMMARY[ask.role] ?? ""} It takes effect straight away.`.trim();
    if (self && ask.role !== "admin") {
      body += " You will no longer be able to manage this organization.";
    }
  } else if (ask.kind === "remove") {
    const self = ask.member.user_id === myId;
    title = self ? "Remove yourself?" : `Remove ${who(ask.member).primary}?`;
    body = self
      ? "You lose access to this organization straight away. An Admin can invite you back."
      : "They lose access to this organization straight away. You can invite them back later.";
  } else {
    title = `Revoke “${ask.grant.label}”?`;
    body =
      "Its token stops working, so nobody can use it to claim Admin here. You can arm a new grant at any time.";
  }
  return (
    <AlertDialogHeader>
      <AlertDialogTitle className="font-serif text-[19px] leading-snug">{title}</AlertDialogTitle>
      <AlertDialogDescription className="text-[14px] leading-relaxed">{body}</AlertDialogDescription>
    </AlertDialogHeader>
  );
}
