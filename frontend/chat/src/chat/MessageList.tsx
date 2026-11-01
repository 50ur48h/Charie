// The message list: user bubbles on the right, assistant rows on the left.
// Each answer renders its own thinking panel from its own message, so
// earlier evidence never moves to a new answer. It follows new messages
// only while the reader is near the bottom; otherwise it offers "Jump to
// latest". A running answer with a live feed renders its streamed blocks;
// the saved answer replaces them on done.
import { useEffect, useRef, useState } from "react";
import { LogoMark, Spinner } from "@charie/shared";
import type { ChatMessage } from "@charie/shared";
import { AnswerActions, AnswerView, MessageStatus, ThinkingPanel } from "@charie/shared";
import type { FeedState } from "@charie/shared";
import { LiveAnswer } from "./LiveAnswer";
import { ScrollToLatest } from "./ScrollToLatest";

const NEAR_BOTTOM_PX = 80;

function AssistantStatus({ message }: { message: ChatMessage }) {
  if (message.status === "thinking" || message.status === "writing") {
    return (
      <div className="flex items-center gap-2 text-[14px] text-muted">
        <Spinner />
        <span role="status">Thinking…</span>
      </div>
    );
  }
  if (message.status === "failed") {
    return <MessageStatus status="failed" />;
  }
  if (message.status === "stopped") {
    return <MessageStatus status="stopped" />;
  }
  return null;
}

export function MessageList({
  messages,
  onFollowUp,
  live,
  showReading = true,
}: {
  messages: ChatMessage[];
  onFollowUp: (text: string) => void;
  live?: { messageId: number; feed: FeedState } | null;
  showReading?: boolean;
}) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(true);

  function measure(): void {
    const el = scrollerRef.current;
    if (el === null) return;
    setStuck(el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX);
  }

  function jumpToLatest(): void {
    const el = scrollerRef.current;
    if (el === null) return;
    el.scrollTop = el.scrollHeight;
    setStuck(true);
  }

  const liveFeed = live?.feed;
  useEffect(() => {
    if (stuck) {
      const el = scrollerRef.current;
      if (el !== null) el.scrollTop = el.scrollHeight;
    }
  }, [messages, stuck, liveFeed]);

  return (
    <div className="messages-view relative min-h-0 flex-1">
      <div
        ref={scrollerRef}
        data-testid="messages"
        onScroll={measure}
        className="h-full overflow-y-auto"
      >
        <div className="messages-wrap mx-auto max-w-[800px] px-7 pt-[18px] pb-10">
          {messages.map((message) =>
            message.role === "user" ? (
              <div key={message.id} className="mb-5 flex justify-end">
                <div className="max-w-[80%] rounded-[20px] bg-bubble px-[18px] py-[10px] text-[15.5px]">
                  {message.text}
                </div>
              </div>
            ) : (
              <div key={message.id} className="mb-5 flex items-start gap-3">
                <span className="mt-0.5 flex-none text-accent" aria-hidden="true">
                  <LogoMark size={26} />
                </span>
                <div className="min-w-0 flex-1">
                  {live?.messageId === message.id ? (
                    <>
                      {live.feed.thinking.lines.length > 0 && (
                        <ThinkingPanel
                          lines={live.feed.thinking.lines}
                          summary={live.feed.thinking.summary}
                          panelId={`thinking-live-${message.id}`}
                        />
                      )}
                      <AssistantStatus message={message} />
                      <LiveAnswer feed={live.feed} onFollowUp={onFollowUp} showReading={showReading} />
                      {live.feed.error !== null && (
                        <p role="alert" className="text-[14.5px] text-bad-ink">
                          {live.feed.error.message}
                        </p>
                      )}
                    </>
                  ) : (
                    <>
                      {message.thinking.length > 0 && (
                        <ThinkingPanel
                          lines={message.thinking}
                          summary={message.summary}
                          panelId={`thinking-${message.id}`}
                        />
                      )}
                      <AssistantStatus message={message} />
                      {message.status === "done" && message.answer !== null && (
                        <AnswerView answer={message.answer} onFollowUp={onFollowUp} showReading={showReading} />
                      )}
                      {message.status === "done" && message.answer !== null && (
                        <AnswerActions messageId={message.id} answer={message.answer} />
                      )}
                    </>
                  )}
                </div>
              </div>
            ),
          )}
        </div>
      </div>
      {!stuck && <ScrollToLatest onJump={jumpToLatest} />}
    </div>
  );
}
