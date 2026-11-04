"""Verified queries: what is shown, when, and how it is framed (arch 5.4)."""

from __future__ import annotations

import uuid

from charie.agent.context import ContextBundle, VerifiedFrame, render
from charie.semantic.verified import MAX_EXAMPLES, VerifiedQuery, matching


def _example(question: str, sql: str = "SELECT 1", notes: str | None = None) -> VerifiedQuery:
    return VerifiedQuery(id=uuid.uuid4(), question=question, sql=sql, notes=notes)


BUSIEST = _example(
    "which shop was busiest last month?",
    "SELECT s.name, count(*) FROM orders o JOIN shops s ON s.id = o.shop_id GROUP BY s.name",
    notes="Join through shop_id; shop names are not unique across regions.",
)
REVENUE = _example(
    "what was revenue by region last quarter?",
    "SELECT r.name, sum(o.total) FROM orders o JOIN shops s ON s.id = o.shop_id "
    "JOIN regions r ON r.id = s.region_id GROUP BY r.name",
)


def _prompt(bundle: ContextBundle) -> str:
    return render(bundle)[0].content


# --- Matching, which decides whether an example is shown at all ---


def test_an_example_is_found_by_the_words_the_question_shares_with_it() -> None:
    found = matching((BUSIEST, REVENUE), "which shop was busiest in March?")

    assert [item.question for item in found] == [BUSIEST.question]


def test_one_shared_word_is_a_coincidence_and_shows_nothing() -> None:
    """The failure that looks most like success."""
    assert matching((BUSIEST,), "how many shops do we have?") == ()


def test_a_question_of_nothing_but_common_words_matches_nothing() -> None:
    """Every content word here is a stopword."""
    assert matching((BUSIEST, REVENUE), "what is it?") == ()


def test_the_closest_example_comes_first() -> None:
    """Scored as a fraction of the stored question's own words."""
    short = _example("busiest shop?")
    long_one = _example("which shop was busiest last month across every region we trade in?")

    found = matching((long_one, short), "which shop was busiest?")

    assert found[0].question == short.question


def test_no_more_than_a_handful_reach_the_prompt() -> None:
    """Past a handful the examples crowd out the table cards."""
    many = tuple(_example(f"which shop was busiest in month {n}?") for n in range(10))

    assert len(matching(many, "which shop was busiest?")) == MAX_EXAMPLES


def test_ties_keep_the_order_they_were_given() -> None:
    """Oldest first, from the caller."""
    first = _example("which shop was busiest?")
    second = _example("which shop was busiest?  ")

    found = matching((first, second), "which shop was busiest?")

    assert [item.id for item in found] == [first.id, second.id]


# --- What the prompt says, and how it says it ---


def test_an_example_reaches_the_prompt_with_its_question_and_its_sql() -> None:
    bundle = ContextBundle(question="which shop was busiest?", verified_applied=(BUSIEST,))

    prompt = _prompt(bundle)

    assert BUSIEST.question in prompt
    assert "JOIN shops s ON s.id = o.shop_id" in prompt


def test_the_reason_is_rendered_before_the_statement() -> None:
    """An example read without its judgement teaches copying."""
    rendered = BUSIEST.render()

    assert "Why this shape" in rendered
    assert rendered.index("Why this shape") < rendered.index("SQL:")


def test_the_prompt_calls_it_an_example_and_not_an_answer() -> None:
    """The whole risk of the feature in one assertion."""
    assert "examples, not answers" in VerifiedFrame
    assert "write the query the question you were asked needs" in VerifiedFrame


def test_examples_render_at_l3_with_the_definitions() -> None:
    """An Admin approved it and the validator judged it against this catalog."""
    bundle = ContextBundle(question="which shop was busiest?", verified_applied=(BUSIEST,))

    assert "[L3] How this organization has answered questions like this" in _prompt(bundle)


def test_a_question_matching_nothing_renders_no_such_layer() -> None:
    """The common case, and it must render exactly as it did before the feature existed."""
    assert "How this organization has answered" not in _prompt(ContextBundle(question="q"))
