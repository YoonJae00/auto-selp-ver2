import json

from cryptography.fernet import Fernet

from config import settings


def _fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))


def encrypt_credentials(credentials: dict[str, str]) -> str:
    payload = json.dumps(credentials, ensure_ascii=True, sort_keys=True)
    token = _fernet().encrypt(payload.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_credentials(encrypted_credentials: str) -> dict[str, str]:
    decrypted = _fernet().decrypt(encrypted_credentials.encode("utf-8"))
    return json.loads(decrypted.decode("utf-8"))
