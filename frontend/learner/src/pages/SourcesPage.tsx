import { Page, PageHeader } from "@charie/shared";
import { DatabaseCard } from "../sources/DatabaseCard";
import { RefreshBanner } from "../sources/RefreshBanner";

// Sources (P04.4 owns the head, the refresh banner and the database card;
// the documents table is P04.5's and the notes card P04.6's).
export function SourcesPage() {
  return (
    <Page>
      <PageHeader
        title="Sources"
        lead="Where Charie learns from. Add or change anything here, then refresh so Charie learns the changes."
      />
      <RefreshBanner />
      <h2 className="section-title" style={{ marginTop: 0 }}>
        Database
      </h2>
      <DatabaseCard />
    </Page>
  );
}
