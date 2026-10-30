import { useState } from "react";
import { useSearchParams } from "react-router";
import {
  Button,
  Card,
  EntryDetail,
  KnowledgeList,
  Page,
  PageHeader,
  SuggestChangeDialog,
  filterEntries,
  groupCounts,
  toast,
  useKnowledge,
  useSuggestChange,
  useKnowledgeEntry,
  type KnowledgeGroup,
} from "@charie/shared";


export function KnowledgePage() {
  const [group, setGroup] = useState<KnowledgeGroup>("all");
  const [query, setQuery] = useState("");
  const [params] = useSearchParams();
  // Deep links (?entry=key) open one entry; unknown keys show the absent state.
  const [selectedKey, setSelectedKey] = useState<string | null>(
    () => params.get("entry") ?? "metric.net_sales",
  );
  const [suggesting, setSuggesting] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const suggest = useSuggestChange();

  const list = useKnowledge();
  const detail = useKnowledgeEntry(selectedKey);
  const entries = filterEntries(list.data?.entries ?? [], group, query);

  function sendSuggestion(text: string): void {
    if (selectedKey === null) return;
    setSaveError(null);
    suggest.mutate(
      { entryKey: selectedKey, text },
      {
        onSuccess: () => {
          setSuggesting(false);
          toast("Sent to the Learner to check.");
        },
        onError: (error) => setSaveError(error.message),
      },
    );
  }

  return (
    <Page>
      <PageHeader
        title="Knowledge"
        lead="Everything Charie has learned about your business, and how sure it is about each thing. To change something, suggest it here; the Learner checks it against the data first."
        actions={
          list.data && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-[12.5px] font-medium text-accent-ink">
              Version {list.data.version?.number ?? "–"}
            </span>
          )
        }
      />
      {list.isError ? (
        <Card padded role="alert">
          <p className="text-[14px]">Couldn&apos;t load the knowledge list.</p>
          <Button variant="ghost" className="mt-2" onClick={() => void list.refetch()}>
            Try again
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <KnowledgeList
            entries={entries}
            counts={groupCounts(list.data?.counts ?? {})}
            needsReview={list.data?.needs_review ?? 0}
            group={group}
            query={query}
            selectedKey={selectedKey}
            onGroupChange={setGroup}
            onQueryChange={setQuery}
            onSelect={setSelectedKey}
          />
          <div>
            {detail.isPending && (
              <Card padded>
                <p className="text-[14px] text-muted" role="status">
                  Loading entry…
                </p>
              </Card>
            )}
            {detail.isError && (
              <Card padded role="alert">
                <p className="text-[14px]">No entry has that key.</p>
                <Button variant="ghost" className="mt-2" onClick={() => void detail.refetch()}>
                  Try again
                </Button>
              </Card>
            )}
            {detail.data && (
              <EntryDetail
                entry={detail.data.entry}
                version={detail.data.version}
                history={detail.data.history}
                onSuggest={() => {
                  setSaveError(null);
                  setSuggesting(true);
                }}
              />
            )}
          </div>
        </div>
      )}
      {suggesting && detail.data && (
        <SuggestChangeDialog
          entryName={detail.data.entry.title}
          saving={suggest.isPending}
          serverError={saveError}
          onSave={(text) => void sendSuggestion(text)}
          onClose={() => {
            setSuggesting(false);
            setSaveError(null);
          }}
        />
      )}
    </Page>
  );
}
