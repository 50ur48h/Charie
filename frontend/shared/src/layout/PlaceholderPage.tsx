import type { ReactNode } from "react";
import { Link } from "react-router";
import { appName } from "../index";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Page, PageHeader } from "./PageHeader";

export function PlaceholderPage({
  app,
  title,
  lead,
  actions,
}: {
  app: "chat" | "learner";
  title: string;
  lead?: string;
  actions?: ReactNode;
}) {
  return (
    <>
      <title>{`${appName(app)} · ${title}`}</title>
      <Page>
        <PageHeader title={title} lead={lead} actions={actions} />
        <Card padded>
          <p className="text-muted">This page is being built.</p>
        </Card>
      </Page>
    </>
  );
}

export function NotFoundPage({ app }: { app: "chat" | "learner" }) {
  return (
    <>
      <title>{`${appName(app)} · Page not found`}</title>
      <Page>
        <PageHeader title="Page not found" lead="That page doesn't exist." />
        <Button asChild>
          <Link to="/">Go to the start</Link>
        </Button>
      </Page>
    </>
  );
}
