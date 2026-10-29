import { Outlet, useLocation } from "react-router";
import {
  AppShell,
  LearnerSidebar,
  useSidebarHidden,
  type LearnerSidebarPage,
} from "@charie/shared";
import { learnerRoutes, useMe } from "@charie/shared";
import { useChatUrl } from "./layout/useChatUrl";
import { useLearnerBadges } from "./layout/useLearnerBadges";

function pageFromPath(pathname: string): LearnerSidebarPage {
  if (pathname.startsWith("/sources")) return "sources";
  if (pathname.startsWith("/learning")) return "learning";
  if (pathname.startsWith("/knowledge")) return "knowledge";
  return "setup";
}

export function LearnerLayout() {
  const [hidden, setHidden] = useSidebarHidden();
  const { pathname } = useLocation();
  const badges = useLearnerBadges();
  const chatUrl = useChatUrl();
  const me = useMe();
  return (
    <AppShell
      app="learner"
      sidebarHidden={hidden}
      onShowSidebar={() => setHidden(false)}
      logoHref={(me.data?.setup_done ?? false) ? learnerRoutes.sources : learnerRoutes.setup}
      sidebar={() => (
        <LearnerSidebar
          active={pageFromPath(pathname)}
          newSources={badges.newDocuments}
          learningLive={badges.learningNow}
          reviewCount={badges.needsReview}
          charieUrl={chatUrl ?? undefined}
          setupDone={me.data?.setup_done ?? false}
        />
      )}
    >
      <Outlet />
    </AppShell>
  );
}
