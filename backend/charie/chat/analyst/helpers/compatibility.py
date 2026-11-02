"""Business-term compatibility: a recipe must fit the term it answers (F1, B020).

A question term with a documented business meaning (below) names
deductions the number must make. A recipe whose meaning states none of
them contradicts the term, so code drops the recipe instead of running
gross for net. No answer keys are read or changed here.
"""

import re

#: Term (lowercase) to its documented source. One entry per owner-approved
#: definition; the PR review approves each line. The gate never defines the
#: term itself: it only blocks a money recipe whose meaning states no
#: subtraction at all.
#:
#: Definition conflict, explicitly unresolved: finance-definitions.docx says
#: "total orders minus refunds" while the practice key subtracts tax and
#: delivery fees. The gate does not depend on which is right: any stated
#: subtraction satisfies it, and none blocks.
HOUSE_TERMS: dict[str, dict] = {
    "net sales": {
        "source": 'finance-definitions.docx: "Net sales means total orders minus refunds."',
        "conflict": "unresolved: refunds (document) versus tax and delivery fees (practice key)",
    },
}


#: Whole words that state a subtraction. Mentioning "tax" or "fees" alone
#: ("including tax and delivery fees") proves nothing; only these show
#: something was taken away.
SUBTRACTION_WORDS = {
    "minus",
    "less",
    "excluding",
    "excluded",
    "excludes",
    "exclude",
    "net",
    "deduct",
    "deducted",
    "deducting",
    "deducts",
    "deduction",
    "subtract",
    "subtracted",
    "subtracting",
    "subtracts",
}


def _words(text: str) -> set[str]:
    """Whole lowercase words; matching never spans word parts."""
    return set(re.findall(r"[a-z]+", text.lower()))


def contradicted_recipe(question, metric_key, meanings, units=None, titles=None) -> str | None:
    """Why this recipe cannot answer this question, or None when it fits.

    Only documented house terms block, and only money measures answering
    for the term itself: naming the metric's own title is an explicit
    owner binding and always wins. A count can never answer a deduction
    term, so counts keep today's behavior. Mentioning a deduction word
    ("including tax") is not a subtraction; only a stated taking-away
    counts. An unknown unit or an unknown/empty meaning cannot justify a
    term that requires a deduction, so the recipe is refused honestly.
    """
    words = _words(question)
    if (units or {}).get(metric_key) != "money":
        return None
    title = (titles or {}).get(metric_key, "") or ""
    if len(title.split()) >= 2 and title.lower() in question.lower():
        return None
    meaning_words = _words(meanings.get(metric_key, "") or "")
    for term, binding in HOUSE_TERMS.items():
        if not set(term.split()) <= words:
            continue
        if meaning_words & SUBTRACTION_WORDS:
            continue
        return (
            f"{metric_key!r} contradicts {term!r}: {binding['source']} "
            "but the recipe meaning states no subtraction."
        )
    return None
