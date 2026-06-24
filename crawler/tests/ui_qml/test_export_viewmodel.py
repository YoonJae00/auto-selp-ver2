from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook

from app.ui_qml.viewmodels.export import ExportViewModel
from app.workers.export import ExportRequest, ExportWorker


def _rows(model):
    return list(model._rows)


def test_empty_supplier_scope_blocks_export_and_error_is_first(tmp_path):
    vm = ExportViewModel(
        supplier_loader=lambda: [SimpleNamespace(id="s1", name="One")],
        scope_loader=lambda supplier_id: (0, 0, []),
        exports_dir=tmp_path,
    )
    vm.setSupplierId("s1")

    assert vm.validateScope() is False
    assert _rows(vm.issues)[0]["severity"] == "error"
    assert vm.canExport is False


def test_warnings_require_acknowledgement_and_scope_change_clears_validation(tmp_path):
    warning = {"severity": "warning", "code": "missing_origin", "message": "원산지 누락", "productId": "p1", "productCode": "P1"}
    vm = ExportViewModel(
        supplier_loader=lambda: [SimpleNamespace(id="s1", name="One"), SimpleNamespace(id="s2", name="Two")],
        scope_loader=lambda supplier_id: (1, 2, [warning]),
        exports_dir=tmp_path,
    )
    vm.setSupplierId("s1")
    assert vm.validateScope() is True
    assert vm.canExport is False
    vm.acknowledgeWarnings(True)
    assert vm.canExport is True
    vm.setSupplierId("s2")
    assert _rows(vm.issues) == []
    assert vm.warningAcknowledged is False
    assert vm.canExport is False


def test_output_path_is_private_and_extension_is_enforced(tmp_path):
    vm = ExportViewModel(supplier_loader=lambda: [], exports_dir=tmp_path)
    vm.setOutputPath(str(tmp_path / "report"))
    assert not hasattr(vm, "outputPath")
    assert vm._output_path == tmp_path / "report.xlsx"


def test_history_is_newest_first_and_corrupt_is_safe(tmp_path):
    old = tmp_path / "old.xlsx"
    wb = Workbook()
    wb.active.title = "products"
    wb.active.append(["header"])
    wb.active.append(["one"])
    wb.save(old)
    bad = tmp_path / "bad.xlsx"
    bad.write_text("not excel")
    os.utime(old, (100, 100))
    os.utime(bad, (200, 200))

    vm = ExportViewModel(supplier_loader=lambda: [], exports_dir=tmp_path)
    rows = _rows(vm.history)
    assert [row["fileName"] for row in rows] == ["bad.xlsx", "old.xlsx"]
    assert rows[0]["outcome"] == "unreadable"
    assert rows[1]["rowCount"] == 1


def test_worker_uses_atomic_replace_and_typed_request(tmp_path):
    final = tmp_path / "result.xlsx"
    request = ExportRequest("s1", final)
    seen = []

    def exporter(session, supplier_id, path):
        seen.append((supplier_id, path))
        path.write_bytes(b"complete")

    worker = ExportWorker(request, session_factory=lambda: SimpleNamespace(close=lambda: None), exporter=exporter)
    worker.run()
    assert final.read_bytes() == b"complete"
    assert seen[0][0] == "s1"
    assert seen[0][1] != final
    assert not seen[0][1].exists()
