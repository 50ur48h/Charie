import type { AnswerBlock } from "@charie/shared";
import {
  CalloutBlock,
  ChartBlock,
  FollowUpsBlock,
  KpisBlock,
  MethodBlock,
  SuggestionsBlock,
  TableBlock,
  TreeBlock,
  type FeedState,
} from "@charie/shared";

function LiveText({ text }: { text: string }) {
  if (text === "") return null;
  return <p className="m-0 mb-4 text-[15.5px] leading-relaxed">{text}</p>;
}

function LiveBlock({
  block,
  index,
  feed,
  onFollowUp,
}: {
  block: AnswerBlock;
  index: number;
  feed: FeedState;
  onFollowUp: (text: string) => void;
}) {
  switch (block.type) {
    case "text": {
      const buffer = feed.texts[index] ?? "";
      if (buffer === "") return null;
      return <LiveText text={buffer} />;
    }
    case "reading":
      return <LiveText text={block.text} />;
    case "callout":
      return <CalloutBlock block={block} />;
    case "suggestions":
      return <SuggestionsBlock block={block} />;
    case "kpis":
      return <KpisBlock block={block} />;
    case "chart":
      return <ChartBlock block={block} />;
    case "table":
      return <TableBlock block={block} />;
    case "tree":
      return <TreeBlock block={block} />;
    case "method":
      return <MethodBlock block={block} />;
    case "follow_ups":
      return <FollowUpsBlock block={block} onFollowUp={onFollowUp} />;
    default:
      return null;
  }
}

// Blocks streamed so far: whole blocks render through their components,
// text blocks show the plain buffer until the saved structured answer
// replaces them on done.
export function LiveAnswer({
  feed,
  onFollowUp,
}: {
  feed: FeedState;
  onFollowUp: (text: string) => void;
}) {
  return (
    <div>
      {feed.blocks.map(
        (block, index) =>
          block !== undefined && (
            <LiveBlock
              key={index}
              block={block}
              index={index}
              feed={feed}
              onFollowUp={onFollowUp}
            />
          ),
      )}
      {feed.choice !== null && (
        <div className="mb-4">
          <p className="m-0 mb-2 text-[15.5px] leading-relaxed">{feed.choice.text}</p>
          <div className="flex flex-wrap gap-2">
            {feed.choice.options.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => onFollowUp(option.label)}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface px-4 py-2 text-[13.5px] font-medium text-text-2 transition-[border-color,color] duration-200 hover:border-focus hover:text-text"
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
