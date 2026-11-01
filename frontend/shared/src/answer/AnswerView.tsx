// One saved answer: all ten block kinds render in order. Anything else
// logs an error and says it is unsupported.
import type { Answer, AnswerBlock } from "./types";
import { CalloutBlock } from "./CalloutBlock";
import { ChartBlock } from "./ChartBlock";
import { FollowUpsBlock } from "./FollowUpsBlock";
import { KpisBlock } from "./KpisBlock";
import { MethodBlock } from "./MethodBlock";
import { ReadingBlock } from "./ReadingBlock";
import { SuggestionsBlock } from "./SuggestionsBlock";
import { TableBlock } from "./TableBlock";
import { TextBlock } from "./TextBlock";
import { TreeBlock } from "./TreeBlock";

// An about answer is one text block plus the method: the method starts
// open so the working-out shows without an extra click.
function methodStartsOpen(blocks: AnswerBlock[]): boolean {
  if (blocks.length !== 2) return false;
  const kinds = new Set(blocks.map((block) => block.type));
  return kinds.size === 2 && kinds.has("text") && kinds.has("method");
}

export function AnswerView({
  answer,
  onFollowUp,
  showReading = true,
}: {
  answer: Answer;
  onFollowUp: (text: string) => void;
  showReading?: boolean;
}) {
  const startOpen = methodStartsOpen(answer.blocks);
  return (
    <div>
      {answer.blocks.map((block, index) => (
        <AnswerBlockView
          key={index}
          block={block}
          onFollowUp={onFollowUp}
          showReading={showReading}
          startOpen={startOpen}
        />
      ))}
    </div>
  );
}

function AnswerBlockView({
  block,
  onFollowUp,
  showReading,
  startOpen,
}: {
  block: AnswerBlock;
  onFollowUp: (text: string) => void;
  showReading: boolean;
  startOpen: boolean;
}) {
  const kind: string = block.type;
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
    case "kpis":
      return <KpisBlock block={block} />;
    case "chart":
      return <ChartBlock block={block} />;
    case "table":
      return <TableBlock block={block} />;
    case "tree":
      return <TreeBlock block={block} />;
    case "method":
      return <MethodBlock block={block} startOpen={startOpen} />;
    default:
      console.error(`Unsupported answer block: ${kind}`);
      return <p className="text-[14px] text-muted">Unsupported block.</p>;
  }
}
