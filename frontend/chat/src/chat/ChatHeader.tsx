// The chat header (Calm chat.html): the chat title and the Thinking mode
// pill. There is no Share button: answers are shared with Copy in P03.8.
export function ChatHeader({ title }: { title: string }) {
  return (
    <header className="grid h-[54px] flex-none grid-cols-[1fr_auto_1fr] items-center px-5">
      <div aria-hidden="true" />
      <h1 className="m-0 truncate text-center text-[14px] font-medium text-text-2">{title}</h1>
      <div className="flex items-center justify-end gap-1">
        <span className="inline-flex items-center gap-2 rounded-full bg-surface-2 px-3 py-[5px] text-[12.5px] whitespace-nowrap text-text-2">
          <span aria-hidden="true" className="size-[7px] rounded-full bg-accent shadow-[0_0_0_3px_var(--accent-soft)]" />
          Thinking mode
        </span>
      </div>
    </header>
  );
}
