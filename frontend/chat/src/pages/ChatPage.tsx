// The chat page frame (P03.2): header, messages, question box, scrolling.
// Answer blocks arrive in P03.4-P03.6 and the live stream in P03.7; until
// then the frame shows the message structure and the thinking state.
import { useState } from "react";
import { Link, useParams } from "react-router";
import {
  ApiError,
  QuestionComposer,
  Spinner,
  toast,
  useChat,
  useFinishMessage,
  useSendMessage,
  useStatus,
} from "@charie/shared";
import { ChatHeader } from "../chat/ChatHeader";
import { MessageList } from "../chat/MessageList";

function isMissingChat(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

function runningAssistantId(messages: { role: string; status: string; id: number }[]): number | undefined {
  const running = messages.find(
    (message) =>
      message.role === "assistant" &&
      (message.status === "thinking" || message.status === "writing"),
  );
  return running?.id;
}

export function ChatPage() {
  const { chatId } = useParams();
  const id = Number(chatId);
  const chatQuery = useChat(Number.isInteger(id) ? id : -1);
  const statusQuery = useStatus();
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [sending, setSending] = useState(false);
  const sendMessage = useSendMessage();
  const finishMessage = useFinishMessage();

  if (chatQuery.isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner label="Loading the chat" />
      </div>
    );
  }

  if (chatQuery.isError) {
    if (isMissingChat(chatQuery.error) || !Number.isInteger(id)) {
      return (
        <div className="mx-auto max-w-[800px] px-7 py-16 text-center">
          <h1 className="font-serif text-[24px] font-semibold">That chat is gone.</h1>
          <p className="mt-2 text-muted">It may have been deleted.</p>
          <Link to="/" className="mt-4 inline-block font-medium text-accent-ink">
            Start a new chat
          </Link>
        </div>
      );
    }
    return (
      <div className="mx-auto max-w-[800px] px-7 py-16 text-center">
        <h1 className="font-serif text-[24px] font-semibold">Couldn&apos;t load the chat.</h1>
        <p className="mt-2 text-muted">
          {chatQuery.error instanceof ApiError
            ? chatQuery.error.message
            : "Something went wrong on our side."}
        </p>
        <button
          type="button"
          onClick={() => void chatQuery.refetch()}
          className="mt-4 cursor-pointer font-medium text-accent-ink"
        >
          Try again
        </button>
      </div>
    );
  }

  const chat = chatQuery.data;
  const draft = drafts[chat.id] ?? "";
  const runningId = runningAssistantId(chat.messages);
  const busy = sending || runningId !== undefined;

  async function submit(): Promise<void> {
    const text = draft.trim();
    if (text === "" || busy) return;
    setSending(true);
    try {
      await sendMessage.mutateAsync({ chatId: chat.id, text });
      setDrafts((prev) => ({ ...prev, [chat.id]: "" }));
    } catch (error) {
      toast(
        error instanceof ApiError
          ? error.message
          : "Something went wrong on our side. Please try again.",
      );
    } finally {
      setSending(false);
    }
  }

  async function finishNow(): Promise<void> {
    if (runningId === undefined || finishMessage.isPending) return;
    try {
      await finishMessage.mutateAsync(runningId);
    } catch (error) {
      toast(
        error instanceof ApiError
          ? error.message
          : "Something went wrong on our side. Please try again.",
      );
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ChatHeader title={chat.title} />
      <MessageList messages={chat.messages} />
      <div className="flex-none px-7 pb-4">
        <div className="mx-auto max-w-[800px]">
          {runningId !== undefined && (
            <div className="mb-2 flex items-center gap-3">
              <button
                type="button"
                onClick={() => void finishNow()}
                disabled={finishMessage.isPending}
                className="cursor-pointer rounded-full border border-border bg-surface px-4 py-[7px] text-[13px] font-medium text-text-2 transition-[border-color,color] duration-200 hover:border-focus hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
              >
                {finishMessage.isPending ? "Finishing…" : "Finish now"}
              </button>
            </div>
          )}
          <QuestionComposer
            value={draft}
            onChange={(value) => setDrafts((prev) => ({ ...prev, [chat.id]: value }))}
            onSubmit={() => void submit()}
            sending={busy}
            dataThrough={statusQuery.data?.data_through}
          />
          <div className="mt-2 text-center text-[12px] text-muted">
            Charie checks every number before showing it.
          </div>
        </div>
      </div>
    </div>
  );
}
