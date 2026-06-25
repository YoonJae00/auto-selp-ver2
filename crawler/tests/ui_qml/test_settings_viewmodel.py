from __future__ import annotations

from app.config import AppConfig
from app.ui_qml.viewmodels.settings import SettingsViewModel


def make_settings_vm(
    *,
    config: AppConfig | None = None,
    keys: dict[str, str] | None = None,
    saved: list[AppConfig] | None = None,
    deleted: list[str] | None = None,
) -> SettingsViewModel:
    key_store = dict(keys or {})
    saved_configs = saved if saved is not None else []
    deleted_keys = deleted if deleted is not None else []

    def load_key(provider: str) -> str | None:
        return key_store.get(provider)

    def save_key(provider: str, api_key: str) -> None:
        key_store[provider] = api_key

    def delete_key(provider: str) -> None:
        deleted_keys.append(provider)
        key_store.pop(provider, None)

    return SettingsViewModel(
        config_loader=lambda: config or AppConfig(),
        config_saver=saved_configs.append,
        key_loader=load_key,
        key_saver=save_key,
        key_deleter=delete_key,
    )


def test_settings_exposes_secret_presence_not_value(qt_app) -> None:
    vm = make_settings_vm(keys={"gemini": "gemini-secret", "openai": "openai-secret"})

    assert vm.geminiKeyConfigured is True
    assert vm.openaiKeyConfigured is True
    assert "secret" not in repr(vm.sections)
    assert "gemini-secret" not in repr(vm.fieldErrors)
    assert not any("secret" in name.data().decode() for name in vm.dynamicPropertyNames())


def test_empty_secret_preserves_existing_key_on_save(qt_app) -> None:
    saved: list[AppConfig] = []
    deleted: list[str] = []
    vm = make_settings_vm(keys={"gemini": "existing-secret"}, saved=saved, deleted=deleted)

    assert vm.save("openai", "chrome", 3, False, True, "", "") is True

    assert saved[-1].llm_provider == "openai"
    assert vm._key_loader("gemini") == "existing-secret"
    assert deleted == []


def test_remove_secret_deletes_key(qt_app) -> None:
    deleted: list[str] = []
    vm = make_settings_vm(keys={"openai": "old-secret"}, deleted=deleted)

    assert vm.removeApiKey("openai") is True

    assert deleted == ["openai"]
    assert vm.openaiKeyConfigured is False


def test_searchable_sections_match_korean_and_english(qt_app) -> None:
    vm = make_settings_vm()

    korean = vm.filterSections("브라우저")
    english = vm.filterSections("browser")

    assert any(section["id"] == "browser" for section in korean)
    assert any(section["id"] == "browser" for section in english)


def test_secret_save_failure_does_not_echo_submitted_key(qt_app) -> None:
    def fail_save_key(provider: str, api_key: str) -> None:
        raise RuntimeError(f"backend rejected {api_key}")

    vm = SettingsViewModel(
        config_loader=lambda: AppConfig(),
        config_saver=lambda _config: None,
        key_loader=lambda _provider: None,
        key_saver=fail_save_key,
        key_deleter=lambda _provider: None,
    )

    assert vm.save("gemini", "msedge", 0, True, True, "TOPSECRET", "") is False
    assert "TOPSECRET" not in repr(vm.fieldErrors)
