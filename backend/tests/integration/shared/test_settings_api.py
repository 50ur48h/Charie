"""GET and PATCH /api/settings: defaults, saves, and exact error messages."""

import pytest

from tests.conftest import log_in

EXPECTED_KEYS = {
    "theme",
    "answer_length",
    "number_format",
    "thinking_minutes",
    "show_reading",
    "memory_on",
    "spend_limit_usd",
    "spend_warn_percent",
    "time_zone",
    "strict_mode",
    "self_test_question_count",
    "setup_done",
}


def test_get_has_defaults_and_no_password_hash(chat_client):
    log_in(chat_client)
    response = chat_client.get("/api/settings")
    assert response.status_code == 200
    settings = response.json()
    assert set(settings) == EXPECTED_KEYS
    assert settings["theme"] == "sage"
    assert settings["time_zone"] is None
    assert "password_hash" not in settings


def test_patch_saves_and_returns_all(chat_client):
    log_in(chat_client)
    response = chat_client.patch("/api/settings", json={"theme": "mist", "thinking_minutes": 5})
    assert response.status_code == 200
    assert response.json()["theme"] == "mist"
    assert response.json()["thinking_minutes"] == 5
    assert chat_client.get("/api/settings").json()["theme"] == "mist"


def test_patch_is_all_or_nothing(chat_client):
    log_in(chat_client)
    response = chat_client.patch("/api/settings", json={"theme": "mist", "thinking_minutes": 99})
    assert response.status_code == 400
    assert chat_client.get("/api/settings").json()["theme"] == "sage"


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("theme", "ocean", "Theme must be one of: sage, lavender, mist, seafoam, mauve, slate."),
        ("answer_length", "long", "Answer length must be short, normal or detailed."),
        ("number_format", "tall", "Number format must be short or full."),
        ("thinking_minutes", 1, "Thinking time must be a whole number of minutes from 2 to 15."),
        ("thinking_minutes", 16, "Thinking time must be a whole number of minutes from 2 to 15."),
        ("thinking_minutes", 2.5, "Thinking time must be a whole number of minutes from 2 to 15."),
        ("thinking_minutes", True, "Thinking time must be a whole number of minutes from 2 to 15."),
        ("show_reading", "yes", "`show_reading` must be true or false."),
        ("memory_on", 1, "`memory_on` must be true or false."),
        ("strict_mode", "no", "`strict_mode` must be true or false."),
        (
            "self_test_question_count",
            0,
            "Practice questions must be a whole number from 1 to 200.",
        ),
        (
            "self_test_question_count",
            201,
            "Practice questions must be a whole number from 1 to 200.",
        ),
        (
            "self_test_question_count",
            "many",
            "Practice questions must be a whole number from 1 to 200.",
        ),
        ("spend_limit_usd", 0, "The monthly limit must be between $0.01 and $100,000."),
        ("spend_limit_usd", 100001, "The monthly limit must be between $0.01 and $100,000."),
        (
            "spend_warn_percent",
            0,
            "The warning level must be a whole number from 1 to 99.",
        ),
        (
            "spend_warn_percent",
            100,
            "The warning level must be a whole number from 1 to 99.",
        ),
        (
            "time_zone",
            "Mars/Olympus",
            "Unknown time zone: `Mars/Olympus`. Use a name like Asia/Kolkata.",
        ),
        ("time_zone", "", "Unknown time zone: ``. Use a name like Asia/Kolkata."),
        ("setup_done", True, "This setting can't be changed here: `setup_done`."),
        ("password_hash", "x", "This setting can't be changed here: `password_hash`."),
        ("no_such_key", 1, "Unknown setting: `no_such_key`."),
    ],
)
def test_each_bad_value_message(chat_client, key, value, message):
    log_in(chat_client)
    response = chat_client.patch("/api/settings", json={key: value})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_setting"
    assert body["message"] == message


def test_valid_time_zone_and_null(chat_client):
    log_in(chat_client)
    assert chat_client.patch("/api/settings", json={"time_zone": "Asia/Kolkata"}).status_code == 200
    assert chat_client.get("/api/settings").json()["time_zone"] == "Asia/Kolkata"
    assert chat_client.patch("/api/settings", json={"time_zone": None}).status_code == 200
    assert chat_client.get("/api/settings").json()["time_zone"] is None


def test_setup_done_and_password_hash_refused(chat_client):
    log_in(chat_client)
    for key in ("setup_done", "password_hash"):
        response = chat_client.patch("/api/settings", json={key: True})
        assert response.status_code == 400
        assert response.json()["message"] == f"This setting can't be changed here: `{key}`."


def test_unknown_key_refused(chat_client):
    log_in(chat_client)
    response = chat_client.patch("/api/settings", json={"no_such_key": 1})
    assert response.status_code == 400
    assert response.json()["message"] == "Unknown setting: `no_such_key`."


def test_both_apps_share_settings(chat_client, learner_client):
    log_in(chat_client)
    assert chat_client.patch("/api/settings", json={"theme": "seafoam"}).status_code == 200
    from tests.conftest import log_in as sign_in

    sign_in(learner_client)
    assert learner_client.get("/api/settings").json()["theme"] == "seafoam"
