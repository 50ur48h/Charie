"""Saved database passwords, encrypted with Fernet (architecture 06, section 6)."""

from cryptography.fernet import Fernet, InvalidToken

from charie.shared.config import ConfigError, require_env


def _fernet() -> Fernet:
    try:
        return Fernet(require_env("CHARIE_ENCRYPTION_KEY").encode("utf-8"))
    except ConfigError:
        raise
    except Exception as err:
        raise ConfigError("Saved passwords can't be read with this CHARIE_ENCRYPTION_KEY.") from err


def encrypt_text(text: str) -> str:
    """Encrypt a password for `data_sources.password_encrypted`."""
    return _fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    """Read a saved password back. A wrong key says so plainly."""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as err:
        raise ConfigError("Saved passwords can't be read with this CHARIE_ENCRYPTION_KEY.") from err
