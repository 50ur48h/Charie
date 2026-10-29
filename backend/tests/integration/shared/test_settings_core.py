"""Settings core: defaults, read, write, and no password hash on the way out."""

from charie.shared.settings import DEFAULTS, get_setting, read_settings, set_setting


def test_defaults_when_nothing_saved(db_session):
    for key, value in DEFAULTS.items():
        assert get_setting(db_session, key) == value
    assert get_setting(db_session, "password_hash") == ""
    assert get_setting(db_session, "time_zone") is None


def test_set_then_get(db_session):
    set_setting(db_session, "theme", "mist")
    assert get_setting(db_session, "theme") == "mist"
    set_setting(db_session, "theme", "sage")
    assert get_setting(db_session, "theme") == "sage"


def test_read_settings_hides_password_hash(db_session):
    set_setting(db_session, "password_hash", "secret-hash")
    settings = read_settings(db_session)
    assert "password_hash" not in settings
    assert settings["theme"] == "sage"
