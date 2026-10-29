import { ArrowRight, Check, CircleAlert, Play } from "lucide-react";
import {
  Button,
  StatCard,
  toast,
  useFinishSetup,
  type Readiness,
} from "@charie/shared";
import { useChatUrl } from "../layout/useChatUrl";
import { useNavigate } from "react-router";

// Step 5: the readiness report. Open Charie finishes setup and moves the
// same tab to the chat app (browsers block a new tab after an await).
// Without a report yet, the step points back at the Learning page.
export function ReadyStep({ readiness }: { readiness: Readiness | null }) {
  const navigate = useNavigate();
  const chatUrl = useChatUrl();
  const finish = useFinishSetup();

  function openCharie(): void {
    finish.mutate(undefined, {
      onSuccess: () => {
        if (chatUrl !== null) window.location.assign(chatUrl);
      },
      onError: (error) => toast(error.message),
    });
  }

  if (readiness === null) {
    return (
      <section aria-label="Charie is ready">
        <h2 className="font-serif text-[24px] font-semibold">Charie is ready</h2>
        <p className="mt-1.5 text-[14.5px] text-muted">Not ready yet</p>
        <p className="mt-1.5 text-[14.5px] text-muted">
          Charie shows how well it did here when learning is finished.
        </p>
        <div className="mt-6">
          <Button variant="primary" size="lg" onClick={() => navigate("/learning")}>
            <Play aria-hidden="true" className="[--icon:16px]" />
            See learning progress
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section aria-label="Charie is ready">
      <div className="grid justify-items-center gap-1 text-center">
        <span
          aria-hidden="true"
          className="grid size-[74px] place-items-center rounded-full bg-accent text-white shadow-[0_0_0_10px_var(--accent-soft)] [--icon:34px]"
        >
          <Check aria-hidden="true" strokeWidth={2.4} />
        </span>
        <h2 className="mt-3.5 font-serif text-[24px] font-semibold">Charie is ready</h2>
        <p className="mt-1.5 max-w-[480px] text-[14.5px] text-muted">
          It learned your business and tested itself. Here&rsquo;s how well it did.
        </p>
      </div>
      <div className="mt-[22px] grid gap-3 text-left sm:grid-cols-3">
        <StatCard
          label="Business numbers checked"
          value={`${readiness.numbers_checked} of ${readiness.numbers_total}`}
          foot={`${readiness.numbers_waiting} wait for your answers`}
        />
        <StatCard
          label="Practice questions right"
          value={`${readiness.practice_right} of ${readiness.practice_total}`}
          foot="The rest are flagged to review"
        />
        <StatCard
          label="Weak area"
          value={readiness.weak_area ?? "None"}
          foot={readiness.weak_area_why ?? "Charie did well everywhere."}
        />
      </div>
      {finish.isError && (
        <p role="alert" className="mt-4 flex items-start gap-2 text-[14px] font-medium text-bad-ink">
          <CircleAlert aria-hidden="true" className="mt-px flex-none [--icon:17px]" />
          {finish.error?.message ?? "Couldn't finish setup."}
        </p>
      )}
      <div className="mt-[14px] grid justify-items-center">
        <Button
          variant="primary"
          size="lg"
          disabled={chatUrl === null || finish.isPending}
          onClick={openCharie}
        >
          {finish.isPending ? "Opening…" : "Open Charie"}
          <ArrowRight aria-hidden="true" className="[--icon:16px]" />
        </Button>
      </div>
    </section>
  );
}
