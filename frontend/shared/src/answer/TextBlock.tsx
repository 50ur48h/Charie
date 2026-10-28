import { Fragment } from "react";
import type { TextBlock as TextBlockType, TextSentence } from "../api/chat-types";
import { Markup } from "./markup";

const PREFIX: Partial<Record<TextSentence["kind"], string>> = {
  possible_reason: "Maybe: ",
  suggestion: "Try: ",
};

function Sentence({ sentence }: { sentence: TextSentence }) {
  const prefix = PREFIX[sentence.kind] ?? "";
  return (
    <>
      {prefix}
      <Markup text={sentence.text} />{" "}
    </>
  );
}

export function TextBlock({ block }: { block: TextBlockType }) {
  return (
    <div className="mb-4 space-y-3 text-[15.5px] leading-relaxed">
      {block.paragraphs.map((paragraph, index) => (
        <p key={index} className="m-0">
          {paragraph.sentences.map((sentence, at) => (
            <Fragment key={at}>
              <Sentence sentence={sentence} />
            </Fragment>
          ))}
        </p>
      ))}
    </div>
  );
}
