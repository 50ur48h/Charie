"""Business-term compatibility: a recipe must fit the term it answers (F1, B020).

A question term with a documented business meaning (below) names
deductions the number must make. A recipe whose meaning states none of
them contradicts the term, so code drops the recipe instead of running
gross for net. No answer keys are read or changed here.
"""

import re

#: Term (lowercase) to its documented deduction words and where they come from.
#: One entry per owner-approved definition; the PR review approves each line.
HOUSE_TERMS: dict[str, dict] = {
    "net sales": {
        # finance-definitions.docx: "Net sales means total orders minus
        # refunds." The practice key subtracts tax and delivery fees too;
        # both sources agree the delivered-amount recipe deducts nothing.
        "source": 'finance-definitions.docx: "Net sales means total orders minus refunds."',
        "requires": [
            "refund",
            "refunds",
            "tax",
            "taxes",
            "fee",
            "fees",
            "discount",
            "discounts",
            "deduct",
            "subtract",
            "minus",
            "adjustment",
        ],
    },
}


def _words(text: str) -> set[str]:
    """Whole lowercase words; matching never spans word parts."""
    return set(re.findall(r"[a-z]+", text.lower()))


def contradicted_recipe(question, metric_key, meanings, units=None) -> str | None:
    """Why this recipe cannot answer this question, or None when it fits.

    Only documented house terms block, and only money measures: a count
    can never answer a deduction term, so counts keep today's behavior.
    An unknown unit or an unknown/empty meaning cannot justify a term
    that requires a deduction.
    """
    words = _words(question)
    if (units or {}).get(metric_key) != "money":
        return None
    meaning = meanings.get(metric_key, "") or ""
    meaning_words = _words(meaning)
    for term, binding in HOUSE_TERMS.items():
        if not set(term.split()) <= words:
            continue
        if any(word in meaning_words for word in binding["requires"]):
            continue
        return (
            f"{metric_key!r} contradicts {term!r}: {binding['source']} "
            "but the recipe meaning states no such deduction."
        )
    return None
