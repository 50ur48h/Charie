import { Navigate, type RouteObject } from "react-router";
import { NotFoundPage, PlaceholderPage } from "@charie/shared";
import { LearnerLayout } from "./LearnerLayout";

export const routes: RouteObject[] = [
  {
    element: <LearnerLayout />,
    children: [
      { index: true, element: <Navigate to="setup" replace /> },
      {
        path: "setup",
        element: (
          <PlaceholderPage
            app="learner"
            title="Set up Charie"
            lead="Five short steps. Charie learns your business before it answers any questions."
          />
        ),
      },
      {
        path: "sources",
        element: (
          <PlaceholderPage
            app="learner"
            title="Sources"
            lead="Where Charie learns from. Add or change anything here, then refresh so Charie learns the changes."
          />
        ),
      },
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
];
