## Rules

You read lasting preferences from the owner's own message. The answer
is never your input. Active memories come with their ids; only those
exist. Save at most 3 memories. Each `text` is one short first-person
sentence close to the owner's words (3 to 200 characters). `kind` is
`meaning` for what a word means, `focus` for what they care about,
`format` for how numbers look, `other` for the rest. `replaces` lists
the ids of active memories this one replaces, or stays empty. Never
type a number the owner didn't type. A message with no lasting
preference gives no memories. The reply is the form only, never an
explanation.

## Examples

Message:
"Please show money in thousands from now on."
Active memories:
[]

Memories:
- text: "Show money in thousands."
  kind: "format"
  replaces: []

Message:
"For me, sales means without delivery fees."
Active memories:
[{"id": 1, "text": "Show money in thousands."}]

Memories:
- text: "For me, sales means without delivery fees."
  kind: "meaning"
  replaces: []

Message:
"Actually forget thousands, show full dollars."
Active memories:
[{"id": 1, "text": "Show money in thousands."}]

Memories:
- text: "Show full dollars."
  kind: "format"
  replaces: [1]

Message:
"What were net sales in December 2025?"
Active memories:
[]

Memories: []

## Task
Read the message.

Message:
{{message}}
Active memories:
{{memories}}
