from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class ListModel(QAbstractListModel):
    def __init__(
        self,
        role_names: Sequence[str],
        rows: list[dict[str, Any]] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        first_role = int(Qt.ItemDataRole.UserRole) + 1
        self._roles = {
            first_role + offset: role_name.encode("utf-8")
            for offset, role_name in enumerate(role_names)
        }
        self._role_keys = {
            role: encoded_name.decode("utf-8") for role, encoded_name in self._roles.items()
        }
        self._rows = self._copy_rows(rows or [])

    @staticmethod
    def _copy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return deepcopy(rows)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        key = self._role_keys.get(role)
        if key is None:
            return None
        return deepcopy(self._rows[index.row()].get(key))

    def roleNames(self) -> dict[int, bytes]:  # noqa: N802
        return dict(self._roles)

    def resetRows(self, rows: list[dict[str, Any]]) -> None:  # noqa: N802
        self.beginResetModel()
        self._rows = self._copy_rows(rows)
        self.endResetModel()
