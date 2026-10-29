"""The replay directory: default and `AI_REPLAY_DIR` override."""

import pathlib

from charie.shared.ai.replay import ReplayStore, default_dir
from charie.shared.config import get_settings


def test_default_folder_is_backend_tests_replays(monkeypatch) -> None:
    monkeypatch.delenv("AI_REPLAY_DIR", raising=False)
    folder = default_dir()
    assert folder.name == "replays"
    assert folder.parent.name == "tests"


def test_default_dir_is_repo_backend_tests_replays(monkeypatch) -> None:
    import charie.shared.ai.replay as replay_module

    monkeypatch.delenv("AI_REPLAY_DIR", raising=False)
    repo = pathlib.Path(replay_module.__file__).resolve().parents[4]
    assert default_dir() == repo / "backend/tests/replays/"


def test_ai_replay_dir_moves_the_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_REPLAY_DIR", str(tmp_path))
    get_settings.cache_clear()
    assert default_dir() == tmp_path
    store = ReplayStore(default_dir())
    store.save("name_chat", "abc123", {"content": "hi"})
    assert (tmp_path / "name_chat" / "abc123.json").is_file()
