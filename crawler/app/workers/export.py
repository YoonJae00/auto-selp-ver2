from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from PySide6.QtCore import QThread, Signal

from app.db.session import get_session
from app.exporters.excel import export_to_excel
from app.exporters.validation import validate_export_scope


@dataclass(frozen=True)
class ExportRequest:
    supplier_id: str
    output_path: Path


class ExportWorker(QThread):
    complete = Signal(str)
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        request: ExportRequest,
        *,
        session_factory: Callable[[], Any] = get_session,
        exporter: Callable[..., Path] = export_to_excel,
        validator: Callable[..., Any] = validate_export_scope,
    ) -> None:
        super().__init__()
        self.request = request
        self._session_factory = session_factory
        self._exporter = exporter
        self._validator = validator

    cancel = QThread.requestInterruption

    def run(self) -> None:
        request = self.request
        output = request.output_path
        temporary = output.with_name(f".{output.name}.{uuid4().hex}.part.xlsx")
        session = None
        try:
            if self.isInterruptionRequested():
                self.cancelled.emit()
                return
            output.parent.mkdir(parents=True, exist_ok=True)
            session = self._session_factory()
            validation = self._validator(session, request.supplier_id)
            if validation.blocking_count:
                raise ValueError(f"내보내기 검증 오류 {validation.blocking_count}건을 먼저 해결하세요.")
            self._exporter(session, request.supplier_id, temporary)
            if self.isInterruptionRequested():
                self.cancelled.emit()
                return
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError("내보내기 파일이 완성되지 않았습니다.")
            os.replace(temporary, output)
            self.complete.emit(str(output))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if session is not None:
                session.close()
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
