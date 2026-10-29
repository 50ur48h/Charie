"""Encryption round trips; wrong and missing keys say so plainly."""

import pytest
from cryptography.fernet import Fernet

from charie.shared.config import ConfigError, get_settings
from charie.shared.crypto import decrypt_text, encrypt_text


def _fresh_key(monkeypatch) -> str:
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("CHARIE_ENCRYPTION_KEY", key)
    get_settings.cache_clear()
    return key


def test_round_trip(monkeypatch) -> None:
    _fresh_key(monkeypatch)
    token = encrypt_text("s3cret-password")
    assert token != "s3cret-password"
    assert decrypt_text(token) == "s3cret-password"


def test_wrong_key_message(monkeypatch) -> None:
    _fresh_key(monkeypatch)
    token = encrypt_text("s3cret-password")
    _fresh_key(monkeypatch)
    with pytest.raises(
        ConfigError,
        match="Saved passwords can't be read with this CHARIE_ENCRYPTION_KEY.",
    ):
        decrypt_text(token)


def test_missing_key_message(monkeypatch) -> None:
    monkeypatch.delenv("CHARIE_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ConfigError, match="CHARIE_ENCRYPTION_KEY is missing"):
        encrypt_text("s3cret-password")
