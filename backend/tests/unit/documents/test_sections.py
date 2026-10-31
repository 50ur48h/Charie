"""Section splitting: headings, whole tables and continuations (P08.3)."""

from charie.shared.documents.sections import (
    CONTINUATION_NOTE,
    MAX_SECTION_CHARS,
    split_sections,
)


def test_headings_and_pages() -> None:
    markdown = (
        "# Refunds\n\nFull refunds within 30 days.\n\n## Exceptions\n\nFinal sale items.\n"
        "\f\n# Shipping\n\nShips in 2 days.\n"
    )
    sections = split_sections(markdown, page_count=3)
    assert [(section.heading_path, section.page_from, section.page_to) for section in sections] == [
        ("Refunds", 1, 1),
        ("Refunds > Exceptions", 1, 1),
        ("Shipping", 2, 2),
    ]
    assert "Full refunds within 30 days." in sections[0].text
    assert "# Refunds" in sections[0].text  # Original lines stay intact.


def test_single_page_gets_page_one() -> None:
    sections = split_sections("# Title\n\nSome text.\n", page_count=1)
    assert len(sections) == 1
    assert (sections[0].page_from, sections[0].page_to) == (1, 1)


def test_unknown_pages_stay_null() -> None:
    sections = split_sections("# A\n\nText.\n\n# B\n\nMore.\n", page_count=4)
    assert all(section.page_from is None and section.page_to is None for section in sections)


def test_table_not_cut_midrow() -> None:
    rows = "\n".join(f"| item{i} | {i} |" for i in range(30))
    markdown = f"# Prices\n\nSome intro.\n\n| item | price |\n| --- | --- |\n{rows}\n"
    sections = split_sections(markdown, page_count=1)
    table_sections = [section for section in sections if "| item" in section.text]
    assert len(table_sections) == 1
    assert table_sections[0].text.count("| item") == 31  # Header plus every row.
    assert table_sections[0].heading_path == "Prices"


def test_long_table_continuation() -> None:
    rows = "\n".join(f"| item{i:04d} | {'x' * 40} |" for i in range(400))
    markdown = f"# Prices\n\n| item | detail |\n| --- | --- |\n{rows}\n"
    sections = split_sections(markdown, page_count=1)
    table_sections = [section for section in sections if "| item" in section.text]
    assert len(table_sections) > 1
    for section in table_sections:
        assert "| item | detail |" in section.text  # Headers repeat.
        assert "| --- | --- |" in section.text
        assert len(section.text) <= MAX_SECTION_CHARS
    for section in table_sections[1:]:
        assert CONTINUATION_NOTE in section.text
    assert CONTINUATION_NOTE not in table_sections[0].text
    kept = sum(section.text.count("| item") - 1 for section in table_sections)
    assert kept == 400  # Every row kept once; headers repeat but are not counted.


def test_blank_input_has_no_sections() -> None:
    assert split_sections("", page_count=1) == []
    assert split_sections("   \n\n  ", page_count=2) == []


def test_small_html_table_stays_whole() -> None:
    markdown = (
        "# Menu\n\n"
        "<table>\n<tr><th>item</th><th>price</th></tr>\n"
        "<tr>\n<td>Margherita</td>\n<td>18.00</td>\n</tr>\n"
        "</table>\n"
    )
    sections = split_sections(markdown, page_count=1)
    assert len(sections) == 1
    assert sections[0].heading_path == "Menu"
    assert "<td>Margherita</td>" in sections[0].text


def test_large_html_table_keeps_rows_and_headers() -> None:
    rows = "\n".join(f"<tr><td>item{i:04d}</td><td>{'x' * 40}</td></tr>" for i in range(400))
    markdown = (
        "# Prices\n\nSome intro.\n\n<table>\n<thead>\n"
        "<tr><th>item</th><th>detail</th></tr>\n</thead>\n<tbody>\n"
        f"{rows}\n</tbody>\n</table>\n"
    )
    sections = split_sections(markdown, page_count=1)
    table_sections = [section for section in sections if "<table" in section.text]
    assert len(table_sections) > 1
    for section in table_sections:
        assert "<th>item</th>" in section.text  # Headers repeat in every chunk.
        assert len(section.text) <= MAX_SECTION_CHARS
        assert section.text.count("<tr>") == section.text.count("</tr>")  # No split rows.
    assert CONTINUATION_NOTE not in table_sections[0].text
    for section in table_sections[1:]:
        assert CONTINUATION_NOTE in section.text
    assert sum(section.text.count("<td>item") for section in table_sections) == 400


def test_fenced_code_is_not_a_table() -> None:
    markdown = "# Guide\n\n```\n| not | a table |\n# not a heading\n```\n\nReal text.\n"
    sections = split_sections(markdown, page_count=1)
    assert len(sections) == 1
    assert sections[0].heading_path == "Guide"
