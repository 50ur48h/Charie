import { Page, PageHeader, useDocuments } from "@charie/shared";
import { DatabaseCard } from "../sources/DatabaseCard";
import { DocumentsCard } from "../sources/DocumentsCard";
import { NotesCard } from "../sources/NotesCard";
import { RefreshBanner } from "../sources/RefreshBanner";

// Sources: head, banner and database card (P04.4), documents (P04.5),
// owner notes (P04.6).
export function SourcesPage() {
  const documents = useDocuments();
  const list = documents.data?.documents ?? [];
  const pages = list.reduce((sum, doc) => sum + (doc.pages ?? 0), 0);
  const countLine =
    list.length === 1 ? "1 document" : `${list.length} documents`;
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
      <h2 className="section-title">
        Documents <span className="section-note">{countLine} · {pages} pages</span>
      </h2>
      <DocumentsCard />
      <h2 className="section-title">
        Your notes <span className="section-note">Owner notes.md · how Charie understood them</span>
      </h2>
      <NotesCard />
    </Page>
  );
}
