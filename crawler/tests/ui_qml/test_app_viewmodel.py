from __future__ import annotations

import pytest
from PySide6.QtCore import QModelIndex, Qt

from app.ui_qml.models.list_model import ListModel
from app.ui_qml.models.task import TaskState
from app.ui_qml.viewmodels.base import sanitize_diagnostic
from app.ui_qml.viewmodels.app import AppViewModel


def test_task_persists_when_navigation_changes() -> None:
    vm = AppViewModel()
    vm.start_task("crawl", "상품 수집")

    vm.navigate("settings")

    assert vm.currentRoute == "settings"
    assert vm.activeTask.key == "crawl"
    assert vm.taskPanelOpen is True
    assert vm.activeTask.state == TaskState.RUNNING.value


def test_cancel_is_not_failure() -> None:
    vm = AppViewModel()
    vm.start_task("crawl", "상품 수집")

    vm.cancel_task("사용자가 취소했습니다")

    assert vm.activeTask.state == TaskState.CANCELLED.value
    assert vm.activeTask.errorMessage == ""


def test_invalid_route_is_ignored_without_emitting_change() -> None:
    vm = AppViewModel()
    changes = 0

    def count_change() -> None:
        nonlocal changes
        changes += 1

    vm.changed.connect(count_change)
    vm.navigate("unknown")

    assert vm.currentRoute == "suppliers"
    assert changes == 0


def test_failure_diagnostic_is_sanitized() -> None:
    vm = AppViewModel()
    vm.start_task("crawl", "상품 수집")

    vm.fail_task("Authorization: Bearer secret-token password=hunter2")

    assert vm.activeTask.state == TaskState.FAILED.value
    assert "secret-token" not in vm.activeTask.errorMessage
    assert "hunter2" not in vm.activeTask.errorMessage
    assert "[REDACTED]" in vm.activeTask.errorMessage


@pytest.mark.parametrize(
    ("diagnostic", "secret"),
    [
        ('{"api_key":"secret"}', "secret"),
        ('{"token": "secret"}', "secret"),
        ('{"password":"secret"}', "secret"),
    ],
)
def test_quoted_json_diagnostic_secrets_are_sanitized(
    diagnostic: str, secret: str
) -> None:
    sanitized = sanitize_diagnostic(diagnostic)

    assert secret not in sanitized
    assert "[REDACTED]" in sanitized


@pytest.mark.parametrize(
    ("diagnostic", "secret", "expected"),
    [
        (
            'Authorization: "Bearer secret-token"',
            "secret-token",
            'Authorization: "[REDACTED]"',
        ),
        (
            '{"password":"abc\\\"def"}',
            "def",
            '{"password":"[REDACTED]"}',
        ),
    ],
)
def test_escaped_or_quoted_diagnostic_secrets_are_fully_sanitized(
    diagnostic: str, secret: str, expected: str
) -> None:
    sanitized = sanitize_diagnostic(diagnostic)

    assert secret not in sanitized
    assert sanitized == expected


def test_task_update_sanitizes_logs_and_exposes_a_copy() -> None:
    vm = AppViewModel()
    vm.start_task("crawl", "상품 수집")

    vm.update_task("상품 분석", 0.25, "api_key=top-secret")
    exposed_logs = vm.activeTask.logs
    exposed_logs.append("caller mutation")

    assert vm.activeTask.stage == "상품 분석"
    assert vm.activeTask.progress == 0.25
    assert vm.activeTask.logs == ["api_key=[REDACTED]"]


def test_list_model_exposes_ordered_roles_and_data() -> None:
    model = ListModel(["name", "status"], [{"name": "Alpha", "status": "ready"}])
    roles = model.roleNames()
    name_role = int(Qt.ItemDataRole.UserRole) + 1
    status_role = name_role + 1

    assert roles == {name_role: b"name", status_role: b"status"}
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), name_role) == "Alpha"
    assert model.data(model.index(0, 0), status_role) == "ready"
    assert model.data(QModelIndex(), name_role) is None
    assert model.data(model.index(0, 0), status_role + 1) is None


def test_list_model_reset_rows_and_defensive_copy() -> None:
    original = [{"name": "Alpha"}]
    model = ListModel(["name"], original)
    original[0]["name"] = "mutated"

    assert model.data(model.index(0, 0), int(Qt.ItemDataRole.UserRole) + 1) == "Alpha"

    replacement = [{"name": "Beta"}, {"name": "Gamma"}]
    model.resetRows(replacement)
    replacement[0]["name"] = "mutated again"

    assert model.rowCount() == 2
    assert model.data(model.index(0, 0), int(Qt.ItemDataRole.UserRole) + 1) == "Beta"


def test_list_model_defensively_copies_nested_input_and_output() -> None:
    role = int(Qt.ItemDataRole.UserRole) + 1
    original = [{"details": {"tags": ["safe"]}}]
    model = ListModel(["details"], original)

    original[0]["details"]["tags"].append("ingress mutation")
    exposed = model.data(model.index(0, 0), role)
    exposed["tags"].append("egress mutation")

    assert model.data(model.index(0, 0), role) == {"tags": ["safe"]}


def test_running_task_cannot_be_overwritten_by_foreign_owner() -> None:
    vm = AppViewModel()
    assert vm.start_task("crawl-crawl", "상품 수집") is True
    assert vm.can_start_task("adapter-probe") is False
    assert vm.start_task("adapter-probe", "사이트 분석") is False
    assert (vm.activeTask.key, vm.activeTask.label) == ("crawl-crawl", "상품 수집")


def test_task_owner_rejects_same_key_foreign_and_stale_terminal() -> None:
    vm = AppViewModel()
    first, second = object(), object()
    assert vm.acquire_task("crawl-crawl", "first", first)
    assert not vm.acquire_task("crawl-crawl", "second", second)
    assert not vm.complete_owned_task(second)
    assert vm.activeTask.label == "first" and vm.activeTask.state == "running"
    assert vm.complete_owned_task(first)
    assert vm.acquire_task("crawl-crawl", "second", second)
    assert not vm.fail_owned_task(first, "stale")
    assert vm.activeTask.label == "second" and vm.activeTask.state == "running"


def test_shared_diagnostic_sanitizer_covers_header_and_json_forms() -> None:
    from app.diagnostics import sanitize_diagnostic
    from app.ui_qml.viewmodels.base import sanitize_diagnostic as compatible_export

    value = ('Authorization: Bearer abc Bearer standalone '
             '{"api_key":"k","access_token":"a","password":"p"}')
    sanitized = sanitize_diagnostic(value)
    assert compatible_export(value) == sanitized
    for secret in ("abc", "standalone", '"k"', '"a"', '"p"'):
        assert secret not in sanitized
    assert sanitized.count("[REDACTED]") >= 5
