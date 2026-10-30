"""Job settings: one row per job, in code so a change is reviewed (03)."""

from dataclasses import dataclass

from charie.shared.ai.errors import AiError


@dataclass(frozen=True)
class JobSettings:
    provider: str
    model: str
    reasoning_effort: str
    max_output_tokens: int
    timeout_seconds: int


# Starting limits by effort (P13.3 tunes them from the test questions).
_EFFORT_LIMITS = {
    "high": (32_000, 300),
    "medium": (16_000, 180),
    "low": (2_000, 60),
}

# Default effort per job, from 03's "Every AI job".
_DEFAULT_EFFORTS = {
    "sort_owner_notes": "high",
    "note_section": "low",
    "extract_doc_facts": "high",
    "compare_facts": "high",
    "explain_table": "high",
    "find_business_terms": "high",
    "write_term_recipe": "high",
    "propose_defaults": "high",
    "write_owner_questions": "high",
    "write_practice_questions": "medium",
    "understand_question": "high",
    "plan_round": "high",
    "write_sql": "high",
    "find_quotes": "medium",
    "check_enough": "high",
    "write_answer": "high",
    "review_answer": "high",
    "extract_memories": "low",
    "name_chat": "low",
    "judge_test_answer": "high",
}


def _settings_for(effort: str) -> JobSettings:
    tokens, timeout = _EFFORT_LIMITS[effort]
    return JobSettings(
        provider="meta",
        model="muse-wonder-1.0",
        reasoning_effort=effort,
        max_output_tokens=tokens,
        timeout_seconds=timeout,
    )


JOB_SETTINGS: dict[str, JobSettings] = {
    job: _settings_for(effort) for job, effort in _DEFAULT_EFFORTS.items()
}

# P07.5 spends high effort on thinking; the sorted list itself stays small.
JOB_SETTINGS["sort_owner_notes"] = JobSettings(
    provider="meta",
    model="muse-wonder-1.0",
    reasoning_effort="high",
    max_output_tokens=16_000,
    timeout_seconds=300,
)


def get_job_settings(job: str) -> JobSettings:
    """The settings for a job, or an error naming the unknown job."""
    try:
        return JOB_SETTINGS[job]
    except KeyError:
        raise AiError("unknown_job", f"Unknown AI job: `{job}`.") from None
