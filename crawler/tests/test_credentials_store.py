from __future__ import annotations

from unittest.mock import patch

from keyring.errors import PasswordDeleteError

from app.credentials.store import (
    delete_llm_api_key,
    delete_supplier_credentials,
    load_llm_api_key,
    load_supplier_credentials,
    save_llm_api_key,
    save_supplier_credentials,
)


def test_save_and_load_supplier_credentials() -> None:
    with patch("app.credentials.store.keyring") as mock_kr:
        save_supplier_credentials("itopic", "user", "pass")
        assert mock_kr.set_password.call_count == 2

        stored: dict[tuple[str, str], str] = {}

        def fake_get(svc: str, key: str) -> str | None:
            return stored.get((svc, key))

        def fake_set(svc: str, key: str, value: str) -> None:
            stored[(svc, key)] = value

        mock_kr.get_password.side_effect = fake_get
        mock_kr.set_password.side_effect = fake_set

        save_supplier_credentials("itopic", "user", "pass")
        result = load_supplier_credentials("itopic")
        assert result == ("user", "pass")


def test_load_supplier_credentials_returns_none_when_missing() -> None:
    with patch("app.credentials.store.keyring") as mock_kr:
        mock_kr.get_password.return_value = None
        assert load_supplier_credentials("itopic") is None


def test_delete_supplier_credentials_swallows_errors() -> None:
    with patch("app.credentials.store.keyring") as mock_kr:
        mock_kr.get_password.return_value = "user"
        mock_kr.delete_password.side_effect = PasswordDeleteError
        delete_supplier_credentials("itopic")
        assert mock_kr.delete_password.call_count == 2


def test_save_and_load_llm_api_key() -> None:
    with patch("app.credentials.store.keyring") as mock_kr:
        save_llm_api_key("openai", "sk-XXX")
        mock_kr.set_password.assert_called_once_with("auto-selp-crawler.llm", "openai", "sk-XXX")
        mock_kr.get_password.return_value = "sk-XXX"
        assert load_llm_api_key("openai") == "sk-XXX"


def test_delete_llm_api_key_swallows_errors() -> None:
    with patch("app.credentials.store.keyring") as mock_kr:
        mock_kr.delete_password.side_effect = PasswordDeleteError
        delete_llm_api_key("openai")
        mock_kr.delete_password.assert_called_once()
