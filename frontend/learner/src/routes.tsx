import { type RouteObject } from "react-router";
import { LoginPage, NotFoundPage, PlaceholderPage, RequireLogin } from "@charie/shared";
import { LearnerIndex } from "./LearnerIndex";
import { LearnerLayout } from "./LearnerLayout";
import { LearningPage } from "./pages/LearningPage";
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
      {
        path: "knowledge",
        element: (
          <PlaceholderPage
            app="learner"
            title="Knowledge"
            lead="Check and fix what Charie learned. Changes go into a draft version, and Charie keeps using the live version until you publish."
          />
        ),
      },
      { path: "*", element: <NotFoundPage app="learner" /> },
    ],
  },
  { path: "login", element: <LoginPage app="learner" /> },
];
