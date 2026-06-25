from __future__ import annotations

import keyring
from keyring.errors import PasswordDeleteError

SERVICE_PREFIX = "auto-selp-crawler"


def _supplier_service(supplier_slug: str) -> str:
    return f"{SERVICE_PREFIX}.supplier.{supplier_slug}"


def save_supplier_credentials(supplier_slug: str, username: str, password: str) -> None:
    service = _supplier_service(supplier_slug)
    keyring.set_password(service, "username", username)
    keyring.set_password(service, username, password)


def load_supplier_credentials(supplier_slug: str) -> tuple[str, str] | None:
    service = _supplier_service(supplier_slug)
    username = keyring.get_password(service, "username")
    if not username:
        return None
    password = keyring.get_password(service, username)
    if not password:
        return None
    return username, password


def delete_supplier_credentials(supplier_slug: str) -> None:
    service = _supplier_service(supplier_slug)
    username = keyring.get_password(service, "username")
    if username:
        try:
            keyring.delete_password(service, username)
        except PasswordDeleteError:
            pass
        try:
            keyring.delete_password(service, "username")
        except PasswordDeleteError:
            pass


def save_llm_api_key(provider: str, api_key: str) -> None:
    keyring.set_password(f"{SERVICE_PREFIX}.llm", provider, api_key)


def load_llm_api_key(provider: str) -> str | None:
    return keyring.get_password(f"{SERVICE_PREFIX}.llm", provider)


def delete_llm_api_key(provider: str) -> None:
    try:
        keyring.delete_password(f"{SERVICE_PREFIX}.llm", provider)
    except PasswordDeleteError:
        pass
