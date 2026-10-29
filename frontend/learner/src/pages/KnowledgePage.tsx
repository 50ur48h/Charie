import { useEffect, useState } from "react";
import {
  Button,
  Card,
  ConfirmDialog,
  EntryDetail,
  KnowledgeList,
  Page,
  PageHeader,
  toast,
  useApproveEntry,
  useEditEntry,
  useKnowledge,
  useKnowledgeEntry,
  useMarkWrong,
  usePublishVersion,
  useVersionChanges,
  useVersions,
  type KnowledgeKind,
} from "@charie/shared";
import { DraftBanner } from "../knowledge/DraftBanner";
import { MarkWrongDialog } from "../knowledge/MarkWrongDialog";
import { ReviewChangesDialog } from "../knowledge/ReviewChangesDialog";
import { TodoList } from "../knowledge/TodoList";
import { VersionsButton, VersionsDialog } from "../knowledge/VersionsDialog";

// The Learner's Knowledge page (P04.8/9): draft banner, to-check items,
// the editable entries list, review changes, versions and publish.
export function KnowledgePage() {
  const [kind, setKind] = useState<KnowledgeKind | "all">("all");
  const [query, setQuery] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [wrongOpen, setWrongOpen] = useState(false);
  const [wrongError, setWrongError] = useState<string | null>(null);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [reviewId, setReviewId] = useState<number | null>(null);
  const [publishNumber, setPublishNumber] = useState<number | null>(null);

  const edit = useEditEntry();
  const approve = useApproveEntry();
  const markWrong = useMarkWrong();
  const publish = usePublishVersion();
  const versions = useVersions();

  const list = useKnowledge({ kind, q: query, version: "draft" });
  const detail = useKnowledgeEntry(selectedKey, "draft");
  const entries = list.data?.entries ?? [];

  // Select the first entry once the draft list loads.
  useEffect(() => {
    if (selectedKey === null && entries.length > 0) setSelectedKey(entries[0].key);
  }, [entries, selectedKey]);

  function select(key: string): void {
    setSelectedKey(key);
    setEditing(false);
    setEditError(null);
  }

  const draft = (versions.data?.versions ?? []).find((version) => version.status === "draft");
  const liveNumber = (versions.data?.versions ?? []).find(
    (version) => version.status === "published",
  )?.number;
  const reviewVersion = (versions.data?.versions ?? []).find(
    (version) => version.id === reviewId,
  );
  const changes = useVersionChanges(reviewId);

  function saveEdit(patch: { title: string; meaning: string }): void {
    if (selectedKey === null) return;
    setEditError(null);
    edit.mutate(
      { key: selectedKey, ...patch },
      {
        onSuccess: () => {
          setEditing(false);
          toast(`Saved in draft version ${draft?.number ?? "…"}.`);
        },
        onError: (error) => setEditError(error.message),
      },
    );
  }

  function approveEntry(): void {
    if (selectedKey === null) return;
    approve.mutate(selectedKey, {
      onSuccess: () => toast("Approved. It goes live in the next version."),
      onError: (error) => toast(error.message),
    });
  }

  function sendWrong(note: string | null): void {
    if (selectedKey === null) return;
    setWrongError(null);
    markWrong.mutate(
      { key: selectedKey, note },
      {
        onSuccess: () => {
          setWrongOpen(false);
          toast("Marked as wrong. The Learner will look at it again.");
        },
        onError: (error) => setWrongError(error.message),
      },
    );
  }

  function publishVersion(number: number): void {
    publish.mutate(number, {
      onSuccess: (data) => {
        setPublishNumber(null);
        setReviewId(null);
        toast(`Version ${data.version.number} is live.`);
      },
      onError: (error) => toast(error.message),
    });
  }

  const counts = Object.fromEntries(
    entries.reduce((acc, entry) => acc.set(entry.kind, (acc.get(entry.kind) ?? 0) + 1), new Map<string, number>()),
  );

  return (
    <Page>
      <PageHeader
        title="Knowledge"
        lead="Check and fix what Charie learned. Changes go into a draft version, and Charie keeps using the live version until you publish."
        actions={<VersionsButton onOpen={() => setVersionsOpen(true)} />}
      />
      <DraftBanner
        onReview={() => draft && setReviewId(draft.id)}
        onPublish={() => draft && setPublishNumber(draft.number)}
      />
      <TodoList />
      {list.isError ? (
        <Card padded role="alert">
          <p className="text-[14px]">Couldn&apos;t load the knowledge list.</p>
          <Button variant="ghost" className="mt-2" onClick={() => void list.refetch()}>
            Try again
          </Button>
        </Card>
      ) : (
        <div className="grid items-start gap-4 min-[1100px]:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <KnowledgeList
            entries={entries}
            counts={{ ...counts, all: entries.length }}
            kind={kind}
            query={query}
            selectedKey={selectedKey}
            editable
            onKindChange={setKind}
            onQueryChange={setQuery}
            onSelect={select}
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
                entry={detail.data}
                version={
                  list.data?.version == null
                    ? null
                    : { number: list.data.version, status: list.data.status ?? "published" }
                }
                editable
                editing={editing}
                savingEdit={edit.isPending}
                editError={editError}
                approving={approve.isPending}
                onSuggest={() => {}}
                onStartEdit={() => {
                  setEditError(null);
                  setEditing(true);
                }}
                onCancelEdit={() => {
                  setEditing(false);
                  setEditError(null);
                }}
                onSaveEdit={saveEdit}
                onApprove={approveEntry}
                onWrong={() => {
                  setWrongError(null);
                  setWrongOpen(true);
                }}
              />
            )}
          </div>
        </div>
      )}
      {wrongOpen && detail.data && (
        <MarkWrongDialog
          entryName={detail.data.name}
          saving={markWrong.isPending}
          serverError={wrongError}
          onSave={(note) => void sendWrong(note)}
          onClose={() => {
            setWrongOpen(false);
            setWrongError(null);
          }}
        />
      )}
      {versionsOpen && versions.data && (
        <VersionsDialog
          versions={versions.data.versions}
          onClose={() => setVersionsOpen(false)}
          onSeeChanges={(number) => {
            const found = versions.data.versions.find((version) => version.number === number);
            if (found) {
              setVersionsOpen(false);
              setReviewId(found.id);
            }
          }}
        />
      )}
      {reviewVersion && (
        <ReviewChangesDialog
          versionNumber={reviewVersion.number}
          changes={changes.data?.changes ?? []}
          isDraft={reviewVersion.status === "draft"}
          publishing={publish.isPending}
          onClose={() => setReviewId(null)}
          onPublish={() => setPublishNumber(reviewVersion.number)}
        />
      )}
      {publishNumber !== null && (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && setPublishNumber(null)}
          title={`Publish version ${publishNumber}?`}
          body={
            liveNumber == null
              ? "Charie starts using it for new questions right away."
              : `Charie starts using it for new questions right away. Questions that are already running finish with version ${liveNumber}.`
          }
          confirmLabel={`Publish version ${publishNumber}`}
          tone="primary"
          onConfirm={() => publishVersion(publishNumber)}
        />
      )}
    </Page>
  );
}
