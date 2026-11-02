import type { AnswerBlock } from "@charie/shared";
import {
  CalloutBlock,
  ChartBlock,
  FollowUpsBlock,
  KpisBlock,
  MethodBlock,
  QuickChoice,
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
  showReading,
}: {
  block: AnswerBlock;
  index: number;
  feed: FeedState;
  onFollowUp: (text: string) => void;
  showReading: boolean;
}) {
  switch (block.type) {
    case "text": {
      const buffer = feed.texts[index] ?? "";
      if (buffer === "") return null;
      return <LiveText text={buffer} />;
    }
    case "reading":
      if (!showReading) return null;
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
  showReading = true,
}: {
  feed: FeedState;
  onFollowUp: (text: string) => void;
  showReading?: boolean;
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
              showReading={showReading}
            />
          ),
      )}
      {feed.choice !== null && (
        <QuickChoice
          text={feed.choice.text}
          options={feed.choice.options}
          chosenLabel={null}
          disabled
          onChoose={() => {}}
        />
      )}
    </div>
  );
}
