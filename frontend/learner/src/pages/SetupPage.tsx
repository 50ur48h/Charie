import { Navigate, useNavigate, useSearchParams } from "react-router";
import { Card, Page, PageHeader, useSetup } from "@charie/shared";
import { DatabaseStep } from "../setup/DatabaseStep";
import { DocumentsStep } from "../setup/DocumentsStep";
import { LearnStep } from "../setup/LearnStep";
import { QuestionsStep } from "../setup/QuestionsStep";
import { ReadyStep } from "../setup/ReadyStep";
import { SetupSteps } from "../setup/SetupSteps";

// The 5-step setup guide. ?step= counts from 1 (the design counts from 0); a
// missing or bad step is replaced with ?step=<SetupState.step>. Once step 5
// is done the guide never shows again: /setup goes to /sources.
export function SetupPage() {
  const setup = useSetup();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  if (setup.isPending) {
    return (
      <Page>
        <p className="text-[14px] text-muted" role="status">
          Loading the setup guide…
        </p>
      </Page>
    );
  }
  if (setup.isError || !setup.data) {
    return (
      <Page>
        <PageHeader
          title="Set up Charie"
          lead="Five short steps. Charie learns your business before it answers any questions."
        />
        <Card padded>
          <p className="text-[14px]" role="alert">
            Couldn&rsquo;t load the setup guide.{" "}
            <button
              type="button"
              className="font-medium text-accent-ink underline-offset-2 hover:underline"
              onClick={() => void setup.refetch()}
            >
              Try again
            </button>
          </p>
        </Card>
      </Page>
    );
  }

  const { setup_done: done, step: current } = setup.data;
  if (done) {
    return <Navigate to="/sources" replace />;
  }

  const wanted = Number(params.get("step"));
  const open = Number.isInteger(wanted) && wanted >= 1 && wanted <= 5 ? wanted : null;
  if (open === null) {
    return <Navigate to={`/setup?step=${current}`} replace />;
  }

  const go = (step: number): void => {
    navigate(`/setup?step=${step}`);
  };

  return (
    <Page>
      <PageHeader
        title="Set up Charie"
        lead="Five short steps. Charie learns your business before it answers any questions."
      />
      <div className="grid items-start gap-4 min-[1200px]:grid-cols-[280px_minmax(0,1fr)]">
        <Card padded={false} className="p-[14px]">
          <SetupSteps current={current} open={open} done={false} onOpen={go} />
        </Card>
        <Card padded>
          {open === 1 && <DatabaseStep onDone={() => go(2)} />}
          {open === 2 && <DocumentsStep onBack={() => go(1)} onNext={() => go(3)} />}
          {open === 3 && <LearnStep onBack={() => go(2)} onNext={() => go(4)} />}
          {open === 4 && <QuestionsStep onBack={() => go(3)} onNext={() => go(5)} />}
          {open === 5 && <ReadyStep readiness={setup.data.readiness} />}
        </Card>
      </div>
    </Page>
  );
}


