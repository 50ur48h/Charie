"""The question checker: counts, the smoke line, and the hidden-file rule."""

from pathlib import Path

from tests.questions import check

FIXTURES = Path(__file__).parent / "fixtures"
QUESTIONS = Path(__file__).resolve().parents[2] / "questions"


def test_public_empty_file_is_valid(capsys) -> None:
    code = check.run(["--set", "public", "--file", str(FIXTURES / "empty.yaml")])
    assert code == 0
    assert "is valid: 0 questions (). Smoke: 0." in capsys.readouterr().out


def test_public_counts_kinds_and_smoke(capsys) -> None:
    code = check.run(["--set", "public", "--file", str(FIXTURES / "good_public.yaml")])
    assert code == 0
    out = capsys.readouterr().out
    assert "is valid: 2 questions (clear 1, vague 1). Smoke: 1." in out


def test_public_problems_exit_1(capsys) -> None:
    code = check.run(["--set", "public", "--file", str(FIXTURES / "bad_duplicate_ids.yaml")])
    assert code == 1
    assert "id is already used." in capsys.readouterr().out


def test_missing_file_exits_1(capsys) -> None:
    code = check.run(["--set", "public", "--file", str(FIXTURES / "missing.yaml")])
    assert code == 1
    assert "Can't read" in capsys.readouterr().out


def test_hidden_missing_file_message(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    code = check.run(["--set", "hidden"])
    assert code == 0
    assert "No hidden file yet. Follow P06.4 to create it." in capsys.readouterr().out


def test_hidden_counts_only(capsys) -> None:
    code = check.run(["--set", "hidden", "--file", str(FIXTURES / "good_hidden.yaml")])
    assert code == 0
    out = capsys.readouterr().out
    assert "Your hidden file is valid: 2 questions (clear 1, follow_up 1)." in out
    assert "delivered" not in out


def test_hidden_problems_show_ids_not_values(capsys) -> None:
    code = check.run(["--set", "hidden", "--file", str(FIXTURES / "bad_hidden_secret.yaml")])
    assert code == 1
    out = capsys.readouterr().out
    assert "Your hidden file has" in out
    assert "SECRETWORD" not in out


def test_template_is_valid(capsys) -> None:
    code = check.run(["--set", "hidden", "--file", str(QUESTIONS / "hidden-template.yaml")])
    assert code == 0
    assert (
        "Your hidden file is valid: 2 questions (clear 1, follow_up 1)." in capsys.readouterr().out
    )


def test_empty_public_file_is_valid(capsys) -> None:
    code = check.run(["--set", "public", "--file", str(QUESTIONS / "public.yaml")])
    assert code == 0
    assert "public.yaml is valid: 0 questions (). Smoke: 0." in capsys.readouterr().out
