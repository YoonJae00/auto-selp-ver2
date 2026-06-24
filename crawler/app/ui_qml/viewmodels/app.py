from __future__ import annotations

from PySide6.QtCore import QObject, Property, Slot

from app.ui_qml.models.task import TaskModel
from app.ui_qml.viewmodels.base import BaseViewModel


class AppViewModel(BaseViewModel):
    VALID_ROUTES = frozenset(
        {"suppliers", "adapter", "crawl", "monitor", "export", "settings"}
    )

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_route = "suppliers"
        self._sidebar_collapsed = False
        self._task_panel_open = False
        self._detail_panel_open = False
        self._active_task = TaskModel(self)

    currentRoute = Property(
        str, lambda self: self._current_route, notify=BaseViewModel.changed
    )
    sidebarCollapsed = Property(
        bool, lambda self: self._sidebar_collapsed, notify=BaseViewModel.changed
    )
    taskPanelOpen = Property(
        bool, lambda self: self._task_panel_open, notify=BaseViewModel.changed
    )
    detailPanelOpen = Property(
        bool, lambda self: self._detail_panel_open, notify=BaseViewModel.changed
    )
    activeTask = Property(QObject, lambda self: self._active_task, constant=True)

    def _set_flag(self, name: str, value: bool) -> None:
        attribute = f"_{name}"
        value = bool(value)
        if getattr(self, attribute) != value:
            setattr(self, attribute, value)
            self.changed.emit()

    @Slot(str)
    def navigate(self, route: str) -> None:
        if route in self.VALID_ROUTES and route != self._current_route:
            self._current_route = route
            self.changed.emit()

    @Slot(bool)
    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        self._set_flag("sidebar_collapsed", collapsed)

    @Slot()
    def toggle_sidebar(self) -> None:
        self.set_sidebar_collapsed(not self._sidebar_collapsed)

    @Slot(bool)
    def set_task_panel_open(self, open_: bool) -> None:
        self._set_flag("task_panel_open", open_)

    @Slot()
    def toggle_task_panel(self) -> None:
        self.set_task_panel_open(not self._task_panel_open)

    @Slot(bool)
    def set_detail_panel_open(self, open_: bool) -> None:
        self._set_flag("detail_panel_open", open_)

    @Slot()
    def toggle_detail_panel(self) -> None:
        self.set_detail_panel_open(not self._detail_panel_open)

    @Slot(str, result=bool)
    def can_start_task(self, key: str) -> bool:
        task = self._active_task
        return task.state not in {"validating", "running"} or task.key == key

    @Slot(str, str, result=bool)
    def start_task(self, key: str, label: str) -> bool:
        if not self.can_start_task(key):
            return False
        self._active_task.start(key, label)
        self.set_task_panel_open(True)
        return True

    @Slot(str)
    @Slot(str, float)
    @Slot(str, float, str)
    def update_task(
        self,
        stage: str,
        progress: float | None = None,
        log: str | None = None,
    ) -> None:
        self._active_task.update(stage, progress, log)

    @Slot()
    def complete_task(self) -> None:
        self._active_task.complete()

    @Slot(str)
    def fail_task(self, message: str) -> None:
        self._active_task.fail(message)

    @Slot(str)
    def cancel_task(self, message: str = "") -> None:
        self._active_task.cancel(message)
