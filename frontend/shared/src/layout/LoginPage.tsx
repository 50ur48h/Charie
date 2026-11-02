import { useRef, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Brain,
  CircleAlert,
  Database,
  Eye,
  EyeOff,
  FileText,
  ListChecks,
  Lock,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { useLogin, useMe } from "../api/hooks";
import { Button, IconButton } from "../components/Button";
import { Field, Input } from "../components/Input";
import { IconBox } from "../components/IconBox";
import { Spinner } from "../components/Spinner";
import { Chart } from "../charts/Chart";
import { sparkOption } from "../charts/spark";
import { appName } from "../index";
import { Brand } from "./Logo";
import { CHAT_APP_URL, LEARNER_APP_URL } from "./appLinks";

// The sample card numbers live here, not in mocks/: they are page copy.
const SAMPLE_QUESTION = "How are we doing this month?";
const SAMPLE_SPARK = [302, 310, 305, 318, 322, 330, 327, 341];

interface LoginCopy {
  headline: string;
  lead: string;
  feats: [LucideIcon, string][];
  sub: string;
  otherPrefix: string;
  otherHref: string;
  otherLabel: string;
}

const COPY: Record<"chat" | "learner", LoginCopy> = {
  chat: {
    headline: "Ask anything about your business. Get answers you can trust.",
    lead: "Charie reads your data and your documents, thinks like an analyst, and checks every number before it shows it.",
    feats: [
      [ShieldCheck, "Checks every number before showing it"],
      [ListChecks, "Shows exactly how it worked each answer out"],
      [BookOpen, "Learns your business first"],
    ],
    sub: "Sign in to Charie.",
    otherPrefix: "Setting Charie up?",
    otherHref: `${LEARNER_APP_URL}/login`,
    otherLabel: "Open Charie Learner",
  },
  learner: {
    headline: "Teach Charie your business.",
    lead: "Connect your data and documents. Charie learns what everything means, tests it, and keeps learning as things change.",
    feats: [
      [Database, "Connect your database, read-only"],
      [FileText, "Add your documents and notes"],
      [Brain, "Charie studies everything and asks you questions"],
    ],
    sub: "Sign in to Charie Learner.",
    otherPrefix: "Looking for the chat?",
    otherHref: `${CHAT_APP_URL}/login`,
    otherLabel: "Sign in to Charie",
  },
};

// The API owns the sign-in words (the mock mirrors them); its message
// wins, and anything else falls back to plain English.
function messageFor(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong on our side. Please try again.";
}

export function LoginPage({ app }: { app: "chat" | "learner" }) {
  const copy = COPY[app];
  const navigate = useNavigate();
  const location = useLocation();
  const client = useQueryClient();
  const me = useMe();
  const login = useLogin();
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const passwordRef = useRef<HTMLInputElement | null>(null);

  const state = location.state as { from?: unknown } | null;
  const from = state?.from;
  const mock = new URLSearchParams(location.search).get("mock");
  const base =
    typeof from === "string" && from.startsWith("/") && from !== "/login" ? from : "/";
  // Learner mock worlds (?mock=new, ?mock=still) survive the sign-in so the
  // store resets to the requested world instead of the saved one.
  const target =
    mock && !base.includes("mock=") ? `${base}${base.includes("?") ? "&" : "?"}mock=${mock}` : base;

  if (me.data?.logged_in) {
    return <Navigate to={target} replace />;
  }

  async function onSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (!password) {
      setError("Please enter the password.");
      passwordRef.current?.focus();
      return;
    }
    setError(null);
    try {
      await login.mutateAsync(password);
      await client.refetchQueries({ queryKey: ["me"] });
      await navigate(target);
    } catch (submitError) {
      setError(messageFor(submitError));
      passwordRef.current?.focus();
    }
  }

  return (
    <>
      <title>{`${appName(app)} · Sign in`}</title>
      <div className="grid min-h-dvh min-[901px]:grid-cols-[1.1fr_1fr]">
        <section
          aria-label="About Charie"
          className="relative flex flex-col overflow-hidden bg-sidebar px-14 py-11 max-[900px]:hidden"
        >
          <span
            aria-hidden="true"
            className="absolute -top-20 right-[-120px] h-[420px] w-[420px] rounded-full bg-accent-soft opacity-70 blur-[60px]"
          />
          <span
            aria-hidden="true"
            className="absolute -bottom-[120px] left-[-140px] h-[380px] w-[380px] rounded-full bg-[color-mix(in_srgb,var(--accent)_22%,transparent)] opacity-70 blur-[60px]"
          />
          <div className="relative z-[1]">
            <Brand app={app} markSize={34} href="/login" />
          </div>
          <h2 className="relative z-[1] mb-0 mt-auto max-w-[520px] font-serif text-[40px] font-semibold leading-[1.15] tracking-[-0.01em]">
            {copy.headline}
          </h2>
          <p className="relative z-[1] mt-3.5 max-w-[480px] text-[16.5px] text-text-2">
            {copy.lead}
          </p>
          <div className="relative z-[1] mt-7 grid gap-3">
            {copy.feats.map(([Icon, text]) => (
              <div key={text} className="flex items-center gap-3 text-[15px] text-text-2">
                <IconBox icon={Icon} />
                {text}
              </div>
            ))}
          </div>
          <div className="relative z-[1] mb-auto mt-8 max-w-[440px] rotate-[-1.5deg] rounded-[18px] border border-border bg-surface px-[18px] py-4 shadow-pop">
            <p className="text-[13px] text-muted">{SAMPLE_QUESTION}</p>
            <p className="mt-1.5 font-serif text-[17px] leading-[1.5]">
              Sales are <mark className="bg-transparent font-semibold text-good-ink">up 6.2%</mark>{" "}
              at <b>$1.42M</b>. The one to watch is{" "}
              <mark className="bg-transparent font-semibold text-bad-ink">
                delivery, down 18.2%
              </mark>
              .
            </p>
            <div aria-hidden="true" className="mt-2 h-[46px]">
              <Chart
                build={(theme) => sparkOption(SAMPLE_SPARK, theme.accent)}
                height={46}
                label="Sample sales trend"
              />
            </div>
          </div>
        </section>
        <section aria-label="Sign in" className="grid place-items-center bg-bg px-7 py-10">
          <form className="w-full max-w-[380px]" onSubmit={onSubmit} noValidate>
            <h1 className="m-0 font-serif text-[30px] font-semibold">Welcome back</h1>
            <p className="mb-[26px] mt-1.5 text-muted">{copy.sub}</p>
            <Field label="Password" htmlFor="password">
              <Input
                id="password"
                inputRef={passwordRef}
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter the password"
                autoComplete="current-password"
                icon={Lock}
                end={
                  <IconButton
                    label={showPassword ? "Hide password" : "Show password"}
                    onClick={() => setShowPassword((shown) => !shown)}
                    className="grid size-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-text"
                  >
                    {showPassword ? <EyeOff /> : <Eye />}
                  </IconButton>
                }
              />
            </Field>
            {error && (
              <p
                role="alert"
                className="mt-2.5 flex items-center gap-2 rounded-[10px] bg-bad-soft px-3 py-2.5 text-[13.5px] text-bad-ink"
              >
                <CircleAlert aria-hidden="true" className="[--icon:16px]" />
                {error}
              </p>
            )}
            <Button
              type="submit"
              variant="primary"
              size="lg"
              block
              disabled={login.isPending}
              className="mt-4"
            >
              {login.isPending ? (
                <>
                  <Spinner label="Signing in" />
                  Signing in…
                </>
              ) : (
                <>
                  Sign in
                  <ArrowRight aria-hidden="true" />
                </>
              )}
            </Button>
            <p className="mt-[18px] text-center text-[13px] text-muted">
              No password? Ask the person who set up Charie.
            </p>
            <p className="mt-[26px] border-t border-border pt-[18px] text-center text-[13.5px] text-muted">
              {copy.otherPrefix}{" "}
              <a href={copy.otherHref} className="font-medium text-accent-ink hover:underline">
                {copy.otherLabel}
              </a>
            </p>
          </form>
        </section>
      </div>
    </>
  );
}
