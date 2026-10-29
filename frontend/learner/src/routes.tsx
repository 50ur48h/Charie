import { type RouteObject } from "react-router";
import { LoginPage, NotFoundPage, RequireLogin } from "@charie/shared";
import { LearnerIndex } from "./LearnerIndex";
import { LearnerLayout } from "./LearnerLayout";
import { LearningPage } from "./pages/LearningPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { SetupPage } from "./pages/SetupPage";
import { SourcesPage } from "./pages/SourcesPage";

export const routes: RouteObject[] = [
  {
    element: (
      <RequireLogin>
        <LearnerLayout />
      </RequireLogin>
    ),
    children: [
      { index: true, element: <LearnerIndex /> },
      { path: "setup", element: <SetupPage /> },
      { path: "sources", element: <SourcesPage /> },
      { path: "learning", element: <LearningPage /> },
      { path: "knowledge", element: <KnowledgePage /> },
      { path: "*", element: <NotFoundPage app="learner" /> },
    ],
  },
  { path: "login", element: <LoginPage app="learner" /> },
];
