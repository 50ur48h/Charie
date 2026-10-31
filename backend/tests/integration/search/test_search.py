"""Three-way search: words, meaning, names, versions and filters (P08.5)."""

from decimal import Decimal

from sqlalchemy import select

from charie.shared.search import search as search_mod
from charie.shared.search.embeddings import EmbeddingResult
from charie.shared.search.search import search_knowledge, search_sections
from charie.shared.tables.knowledge import KbEntry, KbVersion
from charie.shared.tables.sources import Document, DocumentSection

E1 = [1.0] + [0.0] * 1535
E2 = [0.0, 1.0] + [0.0] * 1534
E3 = [0.0, 0.0, 1.0] + [0.0] * 1533


class _StubEmbed:
    """Fixed query vectors; sections carry their own stored vectors."""

    def __init__(self, answers: dict[str, list[float]]):
        self.answers = answers

    def embed_texts(self, texts, **kwargs):
        return EmbeddingResult(
            vectors=[self.answers[text] for text in texts],
            prompt_tokens=len(texts),
            cost_usd=Decimal("0"),
        )


def _add_doc(session, name: str, status: str) -> int:
    row = Document(file_name=name, file_type="md", size_bytes=10, sha256=name, status=status)
    session.add(row)
    session.flush()
    return row.id


def _add_section(session, doc_id: int, position: int, heading: str, text: str, vector) -> int:
    row = DocumentSection(
        document_id=doc_id,
        position=position,
        heading_path=heading,
        text_=text,
        note=f"Note on {heading}.",
        embedding=vector,
    )
    session.add(row)
    session.flush()
    return row.id


def _seed_docs(session) -> dict[str, int]:
    guide = _add_doc(session, "guide.md", "reading")
    refunds = _add_section(
        session, guide, 0, "Refunds", "Full refunds within 30 days, code MEGA0926.", E1
    )
    _add_section(session, guide, 1, "Shipping", "Ships in 2 days.", E2)
    gone = _add_doc(session, "gone.md", "removed")
    _add_section(session, gone, 0, "Gone", "The word ZZZREMOVED lives here.", E3)
    broken = _add_doc(session, "broken.md", "failed")
    _add_section(session, broken, 0, "Broken", "The word ZZZFAILED lives here.", E3)
    session.commit()
    return {"refunds": refunds}


def _seed_knowledge(session) -> tuple[int, int]:
    first = KbVersion(number=1, status="draft", made_by="first_learning")
    second = KbVersion(number=2, status="draft", made_by="first_learning")
    session.add_all([first, second])
    session.flush()
    session.add_all(
        [
            KbEntry(
                version_id=first.id,
                key="term.refund",
                kind="name",
                title="Refund",
                meaning="v1 meaning: money back.",
                confidence="checked",
                sources=[],
            ),
            KbEntry(
                version_id=second.id,
                key="term.refund",
                kind="name",
                title="Refund",
                meaning="v2 meaning: store credit.",
                confidence="checked",
                sources=[],
            ),
        ]
    )
    session.commit()
    return first.id, second.id


def _stub(monkeypatch, answers: dict[str, list[float]]) -> None:
    monkeypatch.setattr(search_mod, "embeddings", _StubEmbed(answers))


def test_words_find_exact_code(db_session, monkeypatch) -> None:
    ids = _seed_docs(db_session)
    _stub(monkeypatch, {"MEGA0926": E3})  # Meaning points elsewhere; words must win.
    hits = search_sections(db_session, "MEGA0926")
    assert hits and hits[0].section_id == ids["refunds"]
    hit = hits[0]
    assert (hit.file_name, hit.heading_path) == ("guide.md", "Refunds")
    assert "MEGA0926" in hit.text


def test_meaning_finds_reworded(db_session, monkeypatch) -> None:
    ids = _seed_docs(db_session)
    _stub(monkeypatch, {"how do returns work": E1})  # No shared words with the text.
    hits = search_sections(db_session, "how do returns work")
    assert hits and hits[0].section_id == ids["refunds"]


def test_names_find_misspelled(db_session, monkeypatch) -> None:
    ids = _seed_docs(db_session)
    _stub(monkeypatch, {"Refuunds": E3})  # Neither words nor meaning match.
    hits = search_sections(db_session, "Refuunds")
    assert ids["refunds"] in [hit.section_id for hit in hits]


def test_removed_and_failed_excluded(db_session, monkeypatch) -> None:
    _seed_docs(db_session)
    removed_id = db_session.scalar(
        select(DocumentSection.id).where(DocumentSection.heading_path == "Gone")
    )
    failed_id = db_session.scalar(
        select(DocumentSection.id).where(DocumentSection.heading_path == "Broken")
    )
    _stub(monkeypatch, {"ZZZREMOVED": E3, "ZZZFAILED": E3})
    assert removed_id is not None and failed_id is not None
    assert removed_id not in [hit.section_id for hit in search_sections(db_session, "ZZZREMOVED")]
    assert failed_id not in [hit.section_id for hit in search_sections(db_session, "ZZZFAILED")]


def test_fusion_dedupes_and_limits(db_session, monkeypatch) -> None:
    ids = _seed_docs(db_session)
    _stub(monkeypatch, {"MEGA0926 refunds": E1})  # All three channels hit refunds.
    hits = search_sections(db_session, "MEGA0926 refunds")
    found = [hit.section_id for hit in hits]
    assert found.count(ids["refunds"]) == 1 and found[0] == ids["refunds"]
    assert len(hits) <= 8


def test_version_filter(db_session, monkeypatch) -> None:
    first_id, second_id = _seed_knowledge(db_session)
    _stub(monkeypatch, {"refund": E1})
    first = search_knowledge(db_session, "refund", first_id)
    second = search_knowledge(db_session, "refund", second_id)
    assert [hit.meaning for hit in first] == ["v1 meaning: money back."]
    assert [hit.meaning for hit in second] == ["v2 meaning: store credit."]


def test_empty_search_returns_nothing(db_session, monkeypatch) -> None:
    _seed_docs(db_session)
    first_id, _ = _seed_knowledge(db_session)
    _stub(monkeypatch, {})
    assert search_sections(db_session, "") == []
    assert search_sections(db_session, "   ") == []
    assert search_knowledge(db_session, "", first_id) == []
