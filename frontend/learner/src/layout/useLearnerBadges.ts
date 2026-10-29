import { useDocuments, useKnowledge, useLearning } from "@charie/shared";

// Live sidebar badges (P04.1): counts from the fake API. Sources counts
// documents that are new or still reading; Learning is a dot while the
// newest run is running; Knowledge counts guessed or conflicting entries
// (the design's "needs review"). Zero hides the badge in the sidebar.
export function useLearnerBadges() {
  const documents = useDocuments();
  const learning = useLearning();
  const knowledge = useKnowledge({ version: "draft" });
  const newDocuments = (documents.data?.documents ?? []).filter(
    (doc) => doc.status === "new" || doc.status === "reading",
  ).length;
  const learningNow = learning.data?.runs?.[0]?.status === "running";
  const needsReview = (knowledge.data?.entries ?? []).filter(
    (entry) => entry.confidence === "guess" || entry.confidence === "conflict",
  ).length;
  return { newDocuments, learningNow, needsReview };
}
