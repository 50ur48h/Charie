// The Settings memory list (P11.5): the real memories with their
// source lines, the empty text and the memory-off note.
import { MessageSquare } from "lucide-react";
import { Button, Card, IconBox, type Memory } from "@charie/shared";

export function MemorySection({
  memories,
  isError,
  onRetry,
  memoryOn,
  onForget,
  onForgetAll,
  forgetting,
  forgettingAll,
}: {
  memories: Memory[] | undefined;
  isError: boolean;
  onRetry: () => void;
  memoryOn: boolean;
  onForget: (id: number) => void;
  onForgetAll: () => void;
  forgetting: boolean;
  forgettingAll: boolean;
}) {
  return (
    <section aria-label="Memory">
      <Card padded>
        <h2 className="card-title">Memory</h2>
        {!memoryOn && (
          <p className="mt-1 text-[13px] text-muted">
            Memory is off. Charie won&apos;t save new preferences or use these until you turn it
            back on.
          </p>
        )}
        <div className="mt-3">
          {isError ? (
            <p className="text-[13.5px] text-muted" role="alert">
              Couldn&apos;t load memories.{" "}
              <button
                type="button"
                className="font-medium text-accent-ink underline-offset-2 hover:underline"
                onClick={onRetry}
              >
                Try again
              </button>
            </p>
          ) : memories === undefined ? (
            <p className="text-[13.5px] text-muted" role="status">
              Loading memories…
            </p>
          ) : memories.length === 0 ? (
            <p className="text-[13.5px] text-muted">
              Nothing remembered yet. Tell Charie a preference in any chat, like what
              &quot;sales&quot; means to you, and it shows up here.
            </p>
          ) : (
            <ul className="grid gap-2">
              {memories.map((memory) => (
                <li
                  key={memory.id}
                  className="flex items-start gap-3 rounded-[12px] bg-surface-2 p-[12px_14px]"
                >
                  <IconBox icon={MessageSquare} />
                  <div className="min-w-0">
                    <div className="font-serif text-[14.5px]">{memory.text}</div>
                    <div className="mt-0.5 text-[12.5px] text-muted">{memory.source}</div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto flex-none"
                    aria-label={`Forget: ${memory.text}`}
                    disabled={forgetting}
                    onClick={() => onForget(memory.id)}
                  >
                    Forget
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {(memories?.length ?? 0) > 0 && (
          <Button
            variant="ghost"
            className="mt-3 text-bad-ink"
            disabled={forgettingAll}
            onClick={onForgetAll}
          >
            Forget everything
          </Button>
        )}
      </Card>
    </section>
  );
}
