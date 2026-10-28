// One saved answer: reading, text, callout, suggestions and follow-ups
// render now; cards, charts, tables, trees and method arrive in P03.5-P03.6.
// Those known-future blocks render nothing until their sub-phase. Anything
// else logs an error and says it is unsupported.
import type { Answer, AnswerBlock } from "./types";
import { CalloutBlock } from "./CalloutBlock";
import { FollowUpsBlock } from "./FollowUpsBlock";
import { ReadingBlock } from "./ReadingBlock";
import { SuggestionsBlock } from "./SuggestionsBlock";
import { TextBlock } from "./TextBlock";

const FUTURE_BLOCKS = new Set(["kpis", "chart", "table", "tree", "method"]);

export function AnswerView({
  answer,
  onFollowUp,
  showReading = true,
}: {
  answer: Answer;
  onFollowUp: (text: string) => void;
  showReading?: boolean;
}) {
  return (
    <div>
      {answer.blocks.map((block, index) => (
        <AnswerBlockView
          key={index}
          block={block}
          onFollowUp={onFollowUp}
          showReading={showReading}
        />
      ))}
    </div>
  );
}

function AnswerBlockView({
  block,
  onFollowUp,
  showReading,
}: {
  block: AnswerBlock;
  onFollowUp: (text: string) => void;
  showReading: boolean;
}) {
  switch (block.type) {
    case "reading":
      return <ReadingBlock block={block} showReading={showReading} />;
    case "text":
      return <TextBlock block={block} />;
    case "callout":
      return <CalloutBlock block={block} />;
    case "suggestions":
      return <SuggestionsBlock block={block} />;
    case "follow_ups":
      return <FollowUpsBlock block={block} onFollowUp={onFollowUp} />;
    default:
      if (FUTURE_BLOCKS.has(block.type)) return null;
      console.error(`Unsupported answer block: ${block.type}`);
      return <p className="text-[14px] text-muted">Unsupported block.</p>;
  }
}
