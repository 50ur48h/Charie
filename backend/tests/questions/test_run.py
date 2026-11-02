"""Runner model flags: Spark default, env wiring, model-aware estimate."""

import argparse
from types import SimpleNamespace

from charie.shared.config import get_settings
from tests.questions.run import SPARK_MODEL, _apply_model_flags, estimate, main


def _question() -> SimpleNamespace:
    return SimpleNamespace(chat=["follow-up"])


def test_estimate_uses_wonder_bands_by_default() -> None:
    assert estimate([_question()]) == (
        "Fresh run of 1 questions (2 answers, 1 judge calls): about $2.02–6.10."
    )


def test_estimate_scales_to_spark() -> None:
    assert estimate([_question()], SPARK_MODEL) == (
        "Fresh run of 1 questions with muse-spark-1.3-contributor "
        "(2 answers, 1 judge calls): about $0.05–0.22."
    )


def test_apply_model_flags_pins_env_and_clears_cache(monkeypatch) -> None:
    monkeypatch.setenv("AI_MODEL", "unused-before")
    monkeypatch.setenv("AI_REASONING_EFFORT", "unused-before")
    args = argparse.Namespace(model="muse-spark-1.3-contributor", effort="high")
    _apply_model_flags(args)
    try:
        assert get_settings().ai_model == "muse-spark-1.3-contributor"
        assert get_settings().ai_reasoning_effort == "high"
    finally:
        get_settings.cache_clear()


def test_runner_defaults_to_spark(capsys) -> None:
    assert main(["--set", "public", "--ids", "clear-001", "--estimate"]) == 0
    assert "muse-spark-1.3-contributor" in capsys.readouterr().out
