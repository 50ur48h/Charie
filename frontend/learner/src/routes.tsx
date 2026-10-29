import { type RouteObject } from "react-router";
import { LoginPage, NotFoundPage, PlaceholderPage, RequireLogin } from "@charie/shared";
import { LearnerIndex } from "./LearnerIndex";
import { LearnerLayout } from "./LearnerLayout";
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
      {
        path: "learning",
        element: (
          <PlaceholderPage
            app="learner"
            title="Learning"
            lead="Live progress while Charie learns, in plain words."
          />
        ),
      },
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
