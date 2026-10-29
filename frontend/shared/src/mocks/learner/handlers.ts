import { http, HttpResponse } from "msw";
import { needSession } from "../session";
import { learner } from "./state";

// Fake learner addresses (mock only). One handler per address; the screens
// read through the real client. Changing documents and runs, timers and the
// draft arrive in later sub-phases — these two lists are read-only for now.
export const LEARNER_DOCUMENTS_URL = "*/api/documents";
export const LEARNER_LEARNING_URL = "*/api/learning";

export const learnerHandlers = [
  http.get(LEARNER_DOCUMENTS_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    const documents = learner()
      .documents.filter((doc) => doc.status !== "removed")
      .sort((a, b) => Date.parse(b.uploaded_at) - Date.parse(a.uploaded_at));
    return HttpResponse.json({ documents });
  }),
  http.get(LEARNER_LEARNING_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    const runs = [...learner().runs].sort(
      (a, b) => Date.parse(b.started_at) - Date.parse(a.started_at),
    );
    return HttpResponse.json({ runs });
  }),
];
