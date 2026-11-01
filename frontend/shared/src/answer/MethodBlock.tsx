import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "../components/Button";
import type { MethodBlock as MethodBlockType } from "../api/chat-types";

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      size="sm"
      className="print:hidden"
      aria-label={copied ? "Copied" : `Copy: ${label}`}
      onClick={() => {
        setCopied(false);
        copyText(text).then((ok) => {
          if (ok) {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
          }
        });
      }}
    >
      {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
      {copied ? "Copied" : "Copy"}
    </Button>
  );
}

function Disclosure({ title, children, startOpen = false }:
  { title: string; children: React.ReactNode; startOpen?: boolean }) {
  const [open, setOpen] = useState(startOpen);
  return (
    <div className="border-b border-border-soft py-2 last:border-b-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
        className="flex w-full cursor-pointer items-center justify-between gap-2 py-1 text-left text-[14px] font-medium text-text-2 hover:text-text"
      >
        {title}
        <span aria-hidden="true" className="text-muted">
          {open ? "−" : "+"}
        </span>
      </button>
      {open && <div className="pb-2 pt-1">{children}</div>}
    </div>
  );
}

// "How I worked this out": definitions, steps, SQL purposes and document
// evidence. Every section expands with a keyboard (native buttons) and
// each query and source copies as plain text. SQL and quotes render as
// text nodes, never HTML.
function PrintEvidence({ block }: { block: MethodBlockType }) {
  // Full evidence for print: the interactive disclosures stay collapsed
  // on screen, so the print layout renders its own always-open copy.
  // Hidden from sighted users and screen readers until printing.
  return (
    <div className="method-print hidden" aria-hidden="true">
      {block.definitions.length > 0 && (
        <div className="method-print-section">
          <h4>What this means</h4>
          <ul>
            {block.definitions.map((definition) => (
              <li key={definition}>{definition}</li>
            ))}
          </ul>
        </div>
      )}
      {block.steps.length > 0 && (
        <div className="method-print-section">
          <h4>Steps</h4>
          <ol>
            {block.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      )}
      {block.queries.length > 0 && (
        <div className="method-print-section">
          <h4>Data used</h4>
          {block.queries.map((query) => (
            <div key={query.purpose}>
              <p>{query.purpose}</p>
              <pre>{query.sql}</pre>
            </div>
          ))}
        </div>
      )}
      {block.sources.length > 0 && (
        <div className="method-print-section">
          <h4>Sources</h4>
          {block.sources.map((source) => (
            <div key={`${source.document}${source.location}`}>
              <p>
                {source.document} · {source.location}
              </p>
              <blockquote>{source.quote}</blockquote>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function MethodBlock({ block, startOpen = false }:
  { block: MethodBlockType; startOpen?: boolean }) {
  return (
    <div className="method-block mb-4 rounded-card border border-border bg-surface px-[18px] py-3 shadow-card">
      <h3 className="m-0 font-serif text-[16px] font-semibold">How I worked this out</h3>
      <div className="method-screen print:hidden">
      <Disclosure title={`What this means (${block.definitions.length})`} startOpen={startOpen}>
        <ul className="m-0 list-disc space-y-1 pl-5 text-[14px] leading-relaxed text-text-2">
          {block.definitions.map((definition) => (
            <li key={definition}>{definition}</li>
          ))}
        </ul>
      </Disclosure>
      <Disclosure title={`Steps (${block.steps.length})`} startOpen={startOpen}>
        <ol className="m-0 list-decimal space-y-1 pl-5 text-[14px] leading-relaxed text-text-2">
          {block.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </Disclosure>
      <Disclosure title={`Data used (${block.queries.length})`} startOpen={startOpen}>
        <div className="space-y-3">
          {block.queries.map((query) => (
            <div key={query.purpose}>
              <div className="flex items-center justify-between gap-2">
                <p className="m-0 text-[14px] font-medium text-text-2">{query.purpose}</p>
                <CopyButton text={`${query.purpose}\n${query.sql}`} label="query" />
              </div>
              <pre className="mt-1 overflow-x-auto rounded-lg bg-surface-2 p-3 font-mono text-[12.5px] leading-relaxed text-text">
                {query.sql}
              </pre>
            </div>
          ))}
        </div>
      </Disclosure>
      <Disclosure title={`Sources (${block.sources.length})`} startOpen={startOpen}>
        <div className="space-y-3">
          {block.sources.map((source) => (
            <div key={`${source.document}${source.location}`}>
              <div className="flex items-center justify-between gap-2">
                <p className="m-0 text-[14px] font-medium text-text-2">
                  {source.document} · {source.location}
                </p>
                <CopyButton
                  text={`${source.quote} (${source.document}, ${source.location})`}
                  label="source"
                />
              </div>
              <blockquote className="m-1 border-l-2 border-border pl-3 text-[14px] italic leading-relaxed text-text-2">
                {source.quote}
              </blockquote>
            </div>
          ))}
        </div>
      </Disclosure>
      </div>
      <PrintEvidence block={block} />
    </div>
  );
}
