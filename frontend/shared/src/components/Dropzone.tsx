import { useRef, useState, type DragEvent } from "react";
import { Upload } from "lucide-react";
import { cn } from "./cn";
import { IconBox } from "./IconBox";

export function Dropzone({
  onFiles,
  title = "Drop files here, or click to choose",
  hint = "Word, PDF, PowerPoint, Excel, Markdown or text. Up to 50 MB each.",
  accept,
  multiple = true,
  disabled,
}: {
  onFiles: (files: File[]) => void;
  title?: string;
  hint?: string;
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function send(files: FileList | File[] | null | undefined) {
    if (disabled || !files) return;
    const list = Array.from(files);
    if (list.length > 0) onFiles(list);
  }

  function onDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDragging(false);
    send(event.dataTransfer?.files);
  }

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        data-dragging={dragging}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false);
        }}
        onDrop={onDrop}
        className={cn(
          "grid w-full place-items-center gap-2 rounded-card border-[1.5px] border-dashed border-muted-2 bg-[color-mix(in_srgb,var(--surface)_60%,transparent)] p-7 text-center text-muted transition-[border-color,background-color] duration-200 not-disabled:hover:border-accent not-disabled:hover:bg-[color-mix(in_srgb,var(--accent-soft)_35%,var(--surface))] disabled:cursor-not-allowed disabled:opacity-50 data-[dragging=true]:border-accent data-[dragging=true]:bg-[color-mix(in_srgb,var(--accent-soft)_35%,var(--surface))]",
        )}
      >
        <IconBox icon={Upload} tone="plain" size={36} />
        <b className="text-[15px] font-semibold text-text">{title}</b>
        <span className="text-[13px]">{hint}</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        hidden
        aria-hidden="true"
        tabIndex={-1}
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={(event) => {
          send(event.target.files);
          event.target.value = "";
        }}
      />
    </>
  );
}
