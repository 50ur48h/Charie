"""Numbers the AI typed that the notes never said (P07.5)."""

from charie.learner.number_check import find_new_numbers, find_numbers


def test_numbers_in_source_are_fine() -> None:
    assert find_new_numbers(["Money is in USD."], "Money is in USD.") == []
    assert find_new_numbers(["Lunch is 11 am to 3 pm."], "Lunch is 11 am to 3 pm.") == []


def test_new_number_is_found() -> None:
    assert find_new_numbers(["Only 5 stores."], "Only stores.") == ["5"]
    assert find_new_numbers(["Target is 28-31%.", "No numbers here."], "Target is low.") == [
        "28-31%",
    ]


def test_matching_ignores_case_and_whitespace() -> None:
    assert find_new_numbers(["  $5  "], "the $5 FEE") == []
    assert find_new_numbers(["1,000 orders"], "1000 orders") == ["1,000"]


def test_find_numbers_reads_tokens_in_order() -> None:
    assert find_numbers("From 1 Jan 2024 to 31 Dec 2025, about 400K rows.") == [
        "1",
        "2024",
        "31",
        "2025",
        "400",
    ]


def test_substring_number_is_new() -> None:
    assert find_new_numbers(["Revenue increased 10%."], "Revenue increased 110%.") == ["10%"]
    assert find_new_numbers(["110%"], "Revenue increased 110%.") == []


def test_signs_units_and_formats_compare_whole() -> None:
    assert find_new_numbers(["-5 degrees"], "minus 5 degrees") == ["-5"]
    assert find_new_numbers(["+5"], "+5 total") == []
    assert find_new_numbers(["The fee is $5."], "the $5 fee") == []
    assert find_new_numbers(["The fee is 5."], "the $5 fee") == ["5"]
    assert find_new_numbers(["1,000.50 total"], "total 1,000.50") == []
    assert find_new_numbers(["28-31%"], "from 28% to 31%") == ["28-31%"]
