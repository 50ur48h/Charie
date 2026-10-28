import { Fragment } from "react";
import type { TextBlock as TextBlockType, TextSentence } from "../api/chat-types";
import { Markup } from "./markup";

function Sentence({ sentence }: { sentence: TextSentence }) {
  // Sentence kinds look the same (architecture 09), except a possible
  // reason carries a small hover hint. No visible prefixes: the sentence
  // text renders exactly as the answer sent it.
  if (sentence.kind === "possible_reason") {
    return (
      <>
        <span title="possible reason">
          <Markup text={sentence.text} />
        </span>{" "}
      </>
    );
  }
  return (
    <>
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
