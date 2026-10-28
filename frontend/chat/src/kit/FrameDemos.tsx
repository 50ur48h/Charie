import { useEffect } from "react";
import { Brain } from "lucide-react";
import {
  AppShell,
  ChatSidebar,
  LearnerSidebar,
  Page,
  PageHeader,
  Pill,
  StatCard,
  useSidebarHidden,
} from "@charie/shared";
import {
  FRAME_CHATS,
  FRAME_CHAT_URL,
  FRAME_LEARNER_USER,
  FRAME_LEARNING_LIVE,
  FRAME_NEW_SOURCES,
  FRAME_QUESTION_COUNT,
  FRAME_REVIEW_COUNT,
  FRAME_USER,
} from "@charie/shared/mocks";

export function ChatFrameDemo() {
  const [hidden, setHidden] = useSidebarHidden();
  useEffect(() => {
    document.title = "Charie · Chat frame";
  }, []);
  return (
    <AppShell
      app="chat"
      sidebar={(place) => (
        <ChatSidebar
          active="usage"
          chats={{ status: "ready", groups: FRAME_CHATS }}
          questionCount={FRAME_QUESTION_COUNT}
          user={FRAME_USER}
          onHide={place === "column" ? () => setHidden(true) : undefined}
        />
      )}
      sidebarHidden={hidden}
      onShowSidebar={() => setHidden(false)}
    >
      <Page>
        <PageHeader
          title="Usage"
          lead="What Charie's AI has cost this month. Every number here comes from the log of each AI call."
          actions={
            <Pill icon={Brain}>
              Model: Muse Wonder
            </Pill>
          }
        />
        <div className="grid gap-[14px] min-[1000px]:grid-cols-4 grid-cols-2">
          <StatCard label="Spent this month" value="$41.20" foot="1–27 Oct" />
          <StatCard label="Questions answered" value="24" foot="About $1.31 each" />
          <StatCard label="Learning runs" value="2" foot="$9.80 in total" />
          <StatCard label="Expected by 31 Oct" value="$47" foot="Well within the credit" />
        </div>
      </Page>
    </AppShell>
  );
}

export function LearnerFrameDemo() {
  useEffect(() => {
    document.title = "Charie Learner · Learner frame";
  }, []);
  return (
    <AppShell
      app="learner"
      sidebar={() => (
        <LearnerSidebar
          active="sources"
          newSources={FRAME_NEW_SOURCES}
          learningLive={FRAME_LEARNING_LIVE}
          reviewCount={FRAME_REVIEW_COUNT}
          user={FRAME_LEARNER_USER}
          charieUrl={FRAME_CHAT_URL}
        />
      )}
      sidebarHidden={false}
      onShowSidebar={() => {}}
    >
      <Page>
        <PageHeader
          title="Sources"
          lead="Where Charie learns from. Add or change anything here, then refresh so Charie learns the changes."
        />
      </Page>
    </AppShell>
  );
}
