from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.diagnostics import sanitize_diagnostic


class ExportHistoryStore:
    def __init__(self, path: Path, *, limit: int = 10) -> None:
        self.path = Path(path)
        self.limit = limit

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError, TypeError):
            return []

    def _write(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(rows[-self.limit:], ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def begin(self, supplier_id: str, supplier_name: str, destination: Path) -> str:
        attempt_id = uuid4().hex
        rows = self._read()
        rows.append({
            "attemptId": attempt_id, "exportedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "supplierId": supplier_id, "supplierName": supplier_name,
            "fileName": Path(destination).name, "path": str(destination), "rowCount": 0,
            "outcome": "pending", "error": "",
        })
        self._write(rows)
        return attempt_id

    def finish(self, attempt_id: str, outcome: str, *, row_count: int = 0, error: str = "") -> None:
        rows = self._read()
        for row in rows:
            if row.get("attemptId") == attempt_id:
                row.update(outcome=outcome, rowCount=int(row_count), error=sanitize_diagnostic(error))
                break
        self._write(rows)

    def latest(self) -> list[dict]:
        return list(reversed(self._read()[-self.limit:]))
