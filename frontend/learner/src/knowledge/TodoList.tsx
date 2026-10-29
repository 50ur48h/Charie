import {
  Button,
  Card,
  Pill,
  toast,
  useDismissTodo,
  useTodos,
  type LearnerTodo,
} from "@charie/shared";
import { timeAgo } from "../lib/when";

const KIND_LABEL: Record<LearnerTodo["kind"], string> = {
  correction: "Correction",
  unknown_word: "Unknown word",
  new_metric: "New business number",
  meaning_change: "Meaning change",
};

// To check (P04.9): the learner's open to-do items. Dismissing marks one
// dismissed; the entry itself never changes.
export function TodoList() {
  const todos = useTodos();
  const dismiss = useDismissTodo();
  const open = todos.data?.todos ?? [];
  if (todos.isPending || todos.isError || open.length === 0) return null;
  return (
    <Card padded className="mb-[18px]">
      <h2 className="card-title">To check</h2>
      <p className="mt-1 text-[13px] text-muted">
        Things you flagged, in a chat or with Mark as wrong. Charie looks at these in the next
        learning run.
      </p>
      <ul className="mt-3 grid gap-2">
        {open.map((todo) => (
          <li
            key={todo.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[10px] bg-surface-2 p-[10px_12px]"
          >
            <Pill tone="outline">{KIND_LABEL[todo.kind]}</Pill>
            <span className="min-w-0 flex-1 basis-[200px] text-[13.5px]">{todo.text}</span>
            <span className="text-[12.5px] text-muted">
              {todo.details.chat_title ? `From “${todo.details.chat_title}”` : "From you"} ·{" "}
              {timeAgo(todo.created_at)}
            </span>
            <Button
              variant="ghost"
              size="sm"
              disabled={dismiss.isPending}
              onClick={() =>
                dismiss.mutate(todo.id, {
                  onSuccess: () => toast("Dismissed. Charie won't look at it."),
                  onError: (error) => toast(error.message),
                })
              }
            >
              Dismiss
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
