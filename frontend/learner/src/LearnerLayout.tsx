import { useState } from "react";
import { Outlet, useLocation } from "react-router";
import {
  AppShell,
  LearnerSidebar,
  SpendingBanner,
  SpendingLimitsDialog,
  useBudgetSettings,
  useSidebarHidden,
  useStatus,
  useUpdateBudgetSettings,
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
  const statusQuery = useStatus();
  const budgetQuery = useBudgetSettings();
  const updateBudget = useUpdateBudgetSettings();
  const [managing, setManaging] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const spending = statusQuery.data?.spending ?? null;
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
      {spending && spending.state !== "ok" && (
        <SpendingBanner spending={spending} onManage={() => {
          setSaveError(null);
          setManaging(true);
        }} />
      )}
      <Outlet />
      {managing && budgetQuery.data && (
        <SpendingLimitsDialog
          limitUsd={budgetQuery.data.spend_limit_usd}
          warnPercent={budgetQuery.data.spend_warn_percent}
          saving={updateBudget.isPending}
          serverError={saveError}
          onSave={(patch) => {
            setSaveError(null);
            updateBudget.mutate(patch, {
              onSuccess: () => setManaging(false),
              onError: (error) => setSaveError(error.message),
            });
          }}
          onClose={() => {
            setManaging(false);
            setSaveError(null);
          }}
        />
      )}
    </AppShell>
  );
}
