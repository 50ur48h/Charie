"""Question topics: ranking, dedup and the twenty-question cap (P09.5)."""

from charie.shared.knowledge.questions import (
    QuestionTopic,
    fingerprint,
    rank_topics,
    select_new,
    topic_reach,
)


def _topic(origin: str, name: str, affects: tuple = ()) -> QuestionTopic:
    return QuestionTopic(origin=origin, topic=name, entry_key=name, affects=affects)


def test_rank() -> None:
    ranked = rank_topics(
        [
            _topic("business", "What returns should mean"),
            _topic("default", "What sales means", ("metric.net_sales",)),
            _topic("default", "What period means"),
            _topic("recipe", "How to fix Orders"),
            _topic("conflict", "Which evidence about profit is right"),
        ]
    )
    assert [item.topic for item in ranked] == [
        "Which evidence about profit is right",
        "How to fix Orders",
        "What sales means",
        "What period means",
        "What returns should mean",
    ]
    assert topic_reach(ranked[2]) == 1


def test_dedup() -> None:
    first = _topic("default", "What sales means", ("metric.net_sales",))
    same = _topic("default", "What sales means", ("metric.net_sales",))
    changed = _topic("default", "What sales means", ("metric.gross_sales",))
    assert fingerprint(first) == fingerprint(same)
    assert fingerprint(first) != fingerprint(changed)
    code = fingerprint(first)
    new, pending = select_new([first, same, changed], [("What sales means", code, "waiting")])
    assert [item.affects for item in new] == [("metric.gross_sales",)]
    assert pending == []


def test_cap_preserves_pending() -> None:
    topics = [_topic("business", f"Topic {number:02d}") for number in range(21)]
    new, pending = select_new(topics, [])
    assert len(new) == 20
    assert [item.topic for item in pending] == ["Topic 20"]
    asked = [(item.topic, fingerprint(item), "waiting") for item in new]
    again, later = select_new(topics, asked)
    assert [item.topic for item in again] == ["Topic 20"]
    assert later == []
