"""Every job in 03 has settings."""

import pytest

from charie.shared.ai.errors import AiError
from charie.shared.ai.jobs import JOB_SETTINGS, get_job_settings

JOBS_03 = [
    "sort_owner_notes",
    "note_section",
    "extract_doc_facts",
    "compare_facts",
    "explain_table",
    "find_business_terms",
    "write_term_recipe",
    "propose_defaults",
    "write_owner_questions",
    "write_practice_questions",
    "understand_question",
    "plan_round",
    "write_sql",
    "find_quotes",
    "check_enough",
    "write_answer",
    "review_answer",
    "extract_memories",
    "name_chat",
    "judge_test_answer",
]


def test_every_job_in_03_has_settings():
    assert sorted(JOB_SETTINGS) == sorted(JOBS_03)
    for settings in JOB_SETTINGS.values():
        assert settings.provider == "meta"
        assert settings.model == "muse-wonder-1.0"


def test_default_efforts_match_03():
    assert get_job_settings("note_section").reasoning_effort == "low"
    assert get_job_settings("extract_memories").reasoning_effort == "low"
    assert get_job_settings("name_chat").reasoning_effort == "low"
    assert get_job_settings("write_practice_questions").reasoning_effort == "medium"
    assert get_job_settings("find_quotes").reasoning_effort == "medium"
    assert get_job_settings("sort_owner_notes").reasoning_effort == "high"
    assert get_job_settings("write_sql").reasoning_effort == "high"
    assert get_job_settings("judge_test_answer").reasoning_effort == "high"
    assert get_job_settings("write_sql").max_output_tokens == 32_000
    assert get_job_settings("write_sql").timeout_seconds == 300
    assert get_job_settings("find_quotes").max_output_tokens == 16_000
    assert get_job_settings("find_quotes").timeout_seconds == 180
    assert get_job_settings("name_chat").max_output_tokens == 2_000
    assert get_job_settings("name_chat").timeout_seconds == 60


def test_unknown_job():
    with pytest.raises(AiError, match="Unknown AI job: `no_such_job`."):
        get_job_settings("no_such_job")
