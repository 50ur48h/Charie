import { FileText } from "lucide-react";
import { Markup } from "../answer/markup";
import type { Evidence } from "./types";

// One question's supporting evidence: a summary, source documents and an
// optional small data table. Values come from fixtures; nothing is computed.
export function QuestionEvidence({ evidence }: { evidence: Evidence }) {
  return (
    <div className="mt-3 rounded-[12px] bg-surface-2 px-[14px] py-3 text-[14px] text-text-2">
      <Markup text={evidence.summary} />
      {evidence.docs && evidence.docs.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {evidence.docs.map((doc) => (
            <span
              key={doc.name}
              className="inline-flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-1 text-[12.5px] font-medium text-text-2"
            >
              <FileText aria-hidden="true" className="[--icon:14px]" />
              {doc.name}
            </span>
          ))}
        </div>
      )}
      {evidence.table && (
        <table className="mt-2 w-full text-[13px]">
          <thead>
            <tr>
              {evidence.table.columns.map((column) => (
                <th key={column} className="border-b border-border px-2 py-1.5 text-left text-xs font-semibold text-muted">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {evidence.table.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className="border-b border-border px-2 py-1.5 text-left tabular-nums">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
