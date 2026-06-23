# Crawler Qt Quick UI/UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crawler's six-screen QWidget interface with a compact, system-themed Qt Quick/QML workspace while preserving crawler behavior and Windows 10/11 packaging.

**Architecture:** Keep crawler, database, credential, adapter, monitor, and export services in Python. Introduce QObject ViewModels as the sole boundary between those services and QML, with one shared task/error model owned by the application ViewModel. Build the UI from project-owned QML controls and tokens, then remove the QWidget entry point only after parity and packaged-platform verification.

**Tech Stack:** Python 3.11, PySide6 6.x, Qt Quick/QML, Qt Quick Controls, SQLAlchemy, pytest, PyInstaller, Inno Setup

---

## File Structure

### Python runtime and shared UI state

- Create `crawler/app/ui_qml/__init__.py` — QML UI package marker.
- Create `crawler/app/ui_qml/application.py` — `QGuiApplication`, QML engine, resource/import paths, root ViewModel registration, startup failure handling.
- Create `crawler/app/ui_qml/viewmodels/base.py` — observable busy/error state helpers and exception sanitization.
- Create `crawler/app/ui_qml/viewmodels/app.py` — navigation, sidebar/detail/task-panel state, active task ownership.
- Create `crawler/app/ui_qml/models/task.py` — task state enum and QObject task model.
- Create `crawler/app/ui_qml/models/list_model.py` — role-based `QAbstractListModel` used by QML lists and tables.
- Create `crawler/app/ui_qml/window_effects.py` — isolated platform capability detection and safe fallback policy.
- Modify `crawler/main.py` — start the QML application instead of `QApplication` plus `MainWindow`.

### Feature ViewModels

- Create `crawler/app/ui_qml/viewmodels/suppliers.py` — supplier CRUD, validation, credentials, list/detail state.
- Create `crawler/app/ui_qml/viewmodels/adapter_studio.py` — four-stage adapter workflow and validation state.
- Create `crawler/app/ui_qml/viewmodels/crawl.py` — category discovery, crawl configuration, task lifecycle, result list.
- Create `crawler/app/ui_qml/viewmodels/monitor.py` — metrics, filters, changes and acknowledgement.
- Create `crawler/app/ui_qml/viewmodels/export.py` — scope, validation, export destination and history.
- Create `crawler/app/ui_qml/viewmodels/settings.py` — searchable settings, secret-presence state, updates.
- Create `crawler/app/ui_qml/viewmodels/first_run.py` — first-run completion state and persistence.

### Worker extraction

- Create `crawler/app/workers/__init__.py` — worker package marker.
- Create `crawler/app/workers/crawl.py` — move `CrawlWorker` out of QWidget code without changing crawl semantics.
- Create `crawler/app/workers/adapter.py` — move picker, probe, generation and test workers out of QWidget code.

### QML resources

- Create `crawler/app/ui_qml/qml/Main.qml` — application window and root composition.
- Create `crawler/app/ui_qml/qml/Theme.qml` — system theme and semantic design tokens.
- Create `crawler/app/ui_qml/qml/qmldir` — singleton/module declaration.
- Create `crawler/app/ui_qml/qml/components/` — `AppShell`, `Sidebar`, `ContentHeader`, `TaskPanel`, `DetailDrawer`, `GlassPanel`, `AppButton`, `AppTextField`, `StatusBadge`, `EmptyState`, `DataTable`, `ToastHost`, `InlineBanner`, and `ConfirmDialog`.
- Create `crawler/app/ui_qml/qml/screens/` — `SuppliersScreen`, `AdapterStudioScreen`, `CrawlScreen`, `MonitorScreen`, `ExportScreen`, `SettingsScreen`, and `FirstRunScreen`.
- Create `crawler/app/ui_qml/qml/icons/` — project-owned SVG navigation and action icons.

### Tests and packaging

- Create `crawler/tests/ui_qml/conftest.py` — offscreen Qt application fixture.
- Create `crawler/tests/ui_qml/test_application.py` — QML startup/import/root-object tests.
- Create one focused test module per ViewModel under `crawler/tests/ui_qml/`.
- Create `crawler/tests/ui_qml/test_window_effects.py` — platform policy tests.
- Modify `crawler/build_windows.spec` — package QML, SVG and Qt Quick modules; remove QSS data after cutover.
- Modify `crawler/README.md` — update UI stack, run instructions and platform behavior.
- Remove `crawler/app/ui/`, including `global.qss`, after parity verification.

## Task 1: QML Runtime Bootstrap

**Files:**
- Create: `crawler/app/ui_qml/__init__.py`
- Create: `crawler/app/ui_qml/application.py`
- Create: `crawler/app/ui_qml/qml/Main.qml`
- Test: `crawler/tests/ui_qml/conftest.py`
- Test: `crawler/tests/ui_qml/test_application.py`
- Modify: `crawler/main.py`

- [ ] **Step 1: Write the failing startup test**

```python
# crawler/tests/ui_qml/test_application.py
from app.ui_qml.application import create_engine


def test_qml_engine_loads_one_root_object(qt_app):
    engine = create_engine()
    assert len(engine.rootObjects()) == 1
    assert engine.rootObjects()[0].objectName() == "appWindow"
```

```python
# crawler/tests/ui_qml/conftest.py
import os

import pytest
from PySide6.QtGui import QGuiApplication


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app
```

- [ ] **Step 2: Run the startup test and verify it fails**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_application.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.ui_qml'`.

- [ ] **Step 3: Add the minimal engine and QML root**

```python
# crawler/app/ui_qml/application.py
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine


QML_ROOT = Path(__file__).resolve().parent / "qml"


def create_engine() -> QQmlApplicationEngine:
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_ROOT))
    engine.load(QUrl.fromLocalFile(str(QML_ROOT / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("QML root object failed to load")
    return engine
```

```qml
// crawler/app/ui_qml/qml/Main.qml
import QtQuick
import QtQuick.Controls

ApplicationWindow {
    objectName: "appWindow"
    width: 1180
    height: 800
    minimumWidth: 900
    minimumHeight: 620
    visible: true
    title: "Auto-Selp Crawler"
}
```

```python
# crawler/main.py replacement inside main()
from PySide6.QtGui import QGuiApplication

from app.db.session import init_db
from app.ui_qml.application import create_engine

init_db()
app = QGuiApplication(sys.argv)
app.setApplicationName("Auto-Selp Crawler")
app.setApplicationDisplayName("Auto-Selp Crawler")
app.setOrganizationName("Auto-Selp")
engine = create_engine()
sys.exit(app.exec())
```

- [ ] **Step 4: Run the startup test and current crawler tests**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_application.py tests/test_paths.py tests/test_credentials_store.py -v`

Expected: all selected tests PASS and no QML import warnings.

- [ ] **Step 5: Commit the runtime bootstrap**

```bash
git add crawler/main.py crawler/app/ui_qml crawler/tests/ui_qml
git commit -m "feat(crawler): bootstrap Qt Quick application"
```

## Task 2: Shared Models and Application ViewModel

**Files:**
- Create: `crawler/app/ui_qml/models/task.py`
- Create: `crawler/app/ui_qml/models/list_model.py`
- Create: `crawler/app/ui_qml/viewmodels/base.py`
- Create: `crawler/app/ui_qml/viewmodels/app.py`
- Test: `crawler/tests/ui_qml/test_app_viewmodel.py`
- Modify: `crawler/app/ui_qml/application.py`

- [ ] **Step 1: Write failing task lifecycle and navigation tests**

```python
from app.ui_qml.models.task import TaskState
from app.ui_qml.viewmodels.app import AppViewModel


def test_task_persists_when_navigation_changes():
    vm = AppViewModel()
    vm.start_task("crawl", "상품 수집")
    vm.navigate("settings")
    assert vm.currentRoute == "settings"
    assert vm.activeTask.key == "crawl"
    assert vm.taskPanelOpen is True
    assert vm.activeTask.state == TaskState.RUNNING.value


def test_cancel_is_not_failure():
    vm = AppViewModel()
    vm.start_task("crawl", "상품 수집")
    vm.cancel_task("사용자가 취소했습니다")
    assert vm.activeTask.state == TaskState.CANCELLED.value
    assert vm.activeTask.errorMessage == ""
```

- [ ] **Step 2: Run tests and verify missing-model failures**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_app_viewmodel.py -v`

Expected: FAIL importing `app.ui_qml.models.task`.

- [ ] **Step 3: Implement the shared task contract**

```python
# crawler/app/ui_qml/models/task.py
from enum import Enum

from PySide6.QtCore import QObject, Property, Signal


class TaskState(str, Enum):
    IDLE = "idle"
    VALIDATING = "validating"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskModel(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._key = ""
        self._label = ""
        self._state = TaskState.IDLE.value
        self._progress = -1.0
        self._stage = ""
        self._error_message = ""
        self._logs: list[str] = []

    key = Property(str, lambda self: self._key, notify=changed)
    label = Property(str, lambda self: self._label, notify=changed)
    state = Property(str, lambda self: self._state, notify=changed)
    progress = Property(float, lambda self: self._progress, notify=changed)
    stage = Property(str, lambda self: self._stage, notify=changed)
    errorMessage = Property(str, lambda self: self._error_message, notify=changed)
    logs = Property("QStringList", lambda self: self._logs, notify=changed)
```

Implement `AppViewModel` with `currentRoute`, `sidebarCollapsed`, `taskPanelOpen`, `detailPanelOpen`, and constant `activeTask` properties. Expose `navigate(route)`, `start_task(key, label)`, `complete_task()`, `fail_task(message)`, and `cancel_task(message)` as Qt slots. Reject routes outside `suppliers`, `adapter`, `crawl`, `monitor`, `export`, and `settings`.

- [ ] **Step 4: Register the root ViewModel and run tests**

```python
# in create_engine()
app_view_model = AppViewModel()
engine.rootContext().setContextProperty("AppVM", app_view_model)
engine.setProperty("appViewModel", app_view_model)  # retain Python ownership
```

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_app_viewmodel.py tests/ui_qml/test_application.py -v`

Expected: all tests PASS; `AppVM.currentRoute` is available to QML.

- [ ] **Step 5: Commit shared UI state**

```bash
git add crawler/app/ui_qml crawler/tests/ui_qml
git commit -m "feat(crawler): add shared QML application state"
```

## Task 3: Design Tokens and Responsive Application Shell

**Files:**
- Create: `crawler/app/ui_qml/qml/Theme.qml`
- Create: `crawler/app/ui_qml/qml/qmldir`
- Create: `crawler/app/ui_qml/qml/components/AppShell.qml`
- Create: `crawler/app/ui_qml/qml/components/Sidebar.qml`
- Create: `crawler/app/ui_qml/qml/components/ContentHeader.qml`
- Create: `crawler/app/ui_qml/qml/components/TaskPanel.qml`
- Create: `crawler/app/ui_qml/qml/components/DetailDrawer.qml`
- Create: `crawler/app/ui_qml/qml/components/GlassPanel.qml`
- Create: `crawler/app/ui_qml/qml/components/AppButton.qml`
- Create: `crawler/app/ui_qml/qml/components/AppTextField.qml`
- Create: `crawler/app/ui_qml/qml/components/StatusBadge.qml`
- Create: `crawler/app/ui_qml/qml/components/EmptyState.qml`
- Create: `crawler/app/ui_qml/qml/components/ToastHost.qml`
- Create: `crawler/app/ui_qml/qml/components/InlineBanner.qml`
- Create: `crawler/app/ui_qml/qml/components/ConfirmDialog.qml`
- Modify: `crawler/app/ui_qml/qml/Main.qml`
- Test: `crawler/tests/ui_qml/test_application.py`

- [ ] **Step 1: Extend the startup test with shell assertions**

```python
def test_root_contains_persistent_shell(qt_app):
    engine = create_engine()
    root = engine.rootObjects()[0]
    assert root.findChild(QObject, "sidebar") is not None
    assert root.findChild(QObject, "contentStack") is not None
    assert root.findChild(QObject, "taskPanel") is not None
```

- [ ] **Step 2: Run the test and verify missing shell objects**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_application.py::test_root_contains_persistent_shell -v`

Expected: FAIL because `sidebar` is not found.

- [ ] **Step 3: Define system-driven tokens**

```qml
// crawler/app/ui_qml/qml/Theme.qml
pragma Singleton
import QtQuick
import QtQuick.Controls

QtObject {
    readonly property bool dark: Application.styleHints.colorScheme === Qt.ColorScheme.Dark
    readonly property color canvas: dark ? "#171717" : "#F3F2EF"
    readonly property color surface: dark ? "#CC242424" : "#DDFDFDFC"
    readonly property color surfaceRaised: dark ? "#E62D2D2D" : "#F2FFFFFF"
    readonly property color border: dark ? "#30FFFFFF" : "#18000000"
    readonly property color text: dark ? "#F2F2F2" : "#20201F"
    readonly property color textMuted: dark ? "#A8A8A8" : "#66635F"
    readonly property color accent: dark ? "#8B9DFF" : "#5366D6"
    readonly property color success: "#3FB98B"
    readonly property color warning: "#E6A84A"
    readonly property color danger: "#E56B6F"
    readonly property int radiusSmall: 8
    readonly property int radiusMedium: 10
    readonly property int radiusLarge: 12
    readonly property int motionFast: 120
    readonly property int motionNormal: 180
}
```

- [ ] **Step 4: Build the shell and shared controls**

Use a `RowLayout` with sidebar and central column, and a conditional right drawer. The central column contains the header, `StackLayout`, and persistent task panel. Set object names exactly to `sidebar`, `contentStack`, and `taskPanel`. Bind sidebar width to `AppVM.sidebarCollapsed ? 64 : 224`; use a 180ms `NumberAnimation` unless reduced motion is active. Every icon-only button must set `Accessible.name` and `ToolTip.text`.

```qml
// Main.qml root content
color: Theme.canvas
AppShell {
    anchors.fill: parent
    viewModel: AppVM
}
```

- [ ] **Step 5: Verify shell loading and theme switching manually**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_application.py -v`

Expected: PASS.

Run: `cd crawler && .venv/bin/python main.py`

Expected: a compact sidebar, empty content area, and collapsed task panel render without QML warnings; changing the OS theme updates canvas and text colors without restart.

- [ ] **Step 6: Commit the design system and shell**

```bash
git add crawler/app/ui_qml/qml crawler/tests/ui_qml/test_application.py
git commit -m "feat(crawler): add responsive QML app shell"
```

## Task 4: Supplier Master-Detail Workflow

**Files:**
- Create: `crawler/app/ui_qml/viewmodels/suppliers.py`
- Create: `crawler/app/ui_qml/qml/screens/SuppliersScreen.qml`
- Create: `crawler/app/ui_qml/qml/components/SupplierEditor.qml`
- Test: `crawler/tests/ui_qml/test_suppliers_viewmodel.py`
- Modify: `crawler/app/ui_qml/application.py`
- Modify: `crawler/app/ui_qml/qml/components/AppShell.qml`

- [ ] **Step 1: Write supplier CRUD and validation tests**

```python
def test_save_rejects_missing_name(suppliers_vm):
    suppliers_vm.beginCreate()
    suppliers_vm.setDraft({"name": "", "base_url": "https://example.com"})
    assert suppliers_vm.saveDraft() is False
    assert suppliers_vm.fieldErrors["name"] == "도매처명을 입력하세요."


def test_create_supplier_saves_secret_without_exposing_it(suppliers_vm, monkeypatch):
    saved = []
    monkeypatch.setattr("app.ui_qml.viewmodels.suppliers.save_supplier_credentials", lambda key, user, password: saved.append((key, user, password)))
    suppliers_vm.beginCreate()
    suppliers_vm.setDraft({"name": "Example", "base_url": "https://example.com", "needs_login": True, "username": "user", "password": "secret"})
    assert suppliers_vm.saveDraft() is True
    assert saved == [("example", "user", "secret")]
    assert "secret" not in str(suppliers_vm.rows)
```

- [ ] **Step 2: Run tests and verify the ViewModel is missing**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_suppliers_viewmodel.py -v`

Expected: FAIL importing `SuppliersViewModel`.

- [ ] **Step 3: Implement supplier presentation and commands**

Create list roles `id`, `name`, `baseUrl`, `needsLogin`, `adapterReady`, `monitorEnabled`, `monitorIntervalHours`, and `lastCrawlAt`. Implement slots `refresh()`, `selectSupplier(id)`, `beginCreate()`, `beginEdit()`, `setDraft(values)`, `saveDraft()`, and `deleteSelected()`. Keep passwords only in the transient draft and clear them after save/cancel.

```python
@Slot(result=bool)
def saveDraft(self) -> bool:
    self._field_errors = validate_supplier_draft(self._draft)
    if self._field_errors:
        self.changed.emit()
        return False
    supplier = persist_supplier(self._draft, self._selected_id)
    persist_supplier_secret_if_present(supplier, self._draft)
    self._draft = {}
    self.refresh()
    return True
```

- [ ] **Step 4: Build and connect the master-detail screen**

The left pane is a selectable supplier list. The center pane shows supplier status and primary actions. `SupplierEditor.qml` opens as a right drawer on wide windows and as an overlay at widths below 1040px. Bind inline validation text to `SuppliersVM.fieldErrors`; do not use native message boxes.

- [ ] **Step 5: Run tests and manually verify create/edit/delete**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_suppliers_viewmodel.py tests/test_credentials_store.py -v`

Expected: PASS.

Run: `cd crawler && .venv/bin/python main.py`

Expected: create, edit, select, delete confirmation, empty state, and keyboard focus order operate correctly.

- [ ] **Step 6: Commit supplier workflow**

```bash
git add crawler/app/ui_qml crawler/tests/ui_qml/test_suppliers_viewmodel.py
git commit -m "feat(crawler): migrate supplier management to QML"
```

## Task 5: Adapter Studio Workflow and Worker Extraction

**Files:**
- Create: `crawler/app/workers/__init__.py`
- Create: `crawler/app/workers/adapter.py`
- Create: `crawler/app/ui_qml/viewmodels/adapter_studio.py`
- Create: `crawler/app/ui_qml/qml/screens/AdapterStudioScreen.qml`
- Create: `crawler/app/ui_qml/qml/components/StageRail.qml`
- Create: `crawler/app/ui_qml/qml/components/MappingTable.qml`
- Create: `crawler/app/ui_qml/qml/components/YamlEditor.qml`
- Test: `crawler/tests/ui_qml/test_adapter_studio_viewmodel.py`
- Modify: `crawler/app/ui_qml/application.py`
- Modify: `crawler/app/ui_qml/qml/components/AppShell.qml`

- [ ] **Step 1: Write workflow-state and stale-validation tests**

```python
def test_generated_yaml_requires_validation_before_save(adapter_vm):
    adapter_vm.acceptGeneratedYaml("adapter:\n  name: sample\n")
    assert adapter_vm.currentStage == 2
    assert adapter_vm.validationStale is True
    assert adapter_vm.canSave is False


def test_editing_validated_yaml_marks_result_stale(adapter_vm):
    adapter_vm.acceptGeneratedYaml("adapter:\n  name: sample\n")
    adapter_vm.acceptValidation({"valid": True, "errors": []})
    adapter_vm.setYamlText("adapter:\n  name: changed\n")
    assert adapter_vm.validationStale is True
    assert adapter_vm.canSave is False
```

- [ ] **Step 2: Run tests and verify missing workflow state**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_adapter_studio_viewmodel.py -v`

Expected: FAIL importing `AdapterStudioViewModel`.

- [ ] **Step 3: Extract UI-independent workers**

Move the existing `PickerWorker`, `TestWorker`, probe callback plumbing, and generation callback plumbing from `app/ui/tabs/adapter_builder_tab.py` to `app/workers/adapter.py`. Preserve their signal signatures and async bodies. Remove all `QWidget`, table, label, and dialog dependencies from the new module. Give the worker layer only input dataclasses and emitted result objects.

```python
class AdapterTestWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            self.completed.emit(loop.run_until_complete(self._run_test()))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            loop.close()
```

- [ ] **Step 4: Implement the four-stage ViewModel**

Expose stage values `0=connect`, `1=analyze`, `2=map`, `3=validate`. Keep `yamlText`, `yamlDirty`, `validationStale`, `validationSummary`, `mappingRows`, `probeSummary`, and `canSave` observable. Starting probe/generation/testing must create or update the shared `AppVM.activeTask`. Hash YAML content after successful validation and compare that hash before save.

- [ ] **Step 5: Build the Site Studio screen**

Use a persistent four-stage rail. Put URL/login inputs in Connect, probe results in Analyze, field mappings in Map, and test/save controls in Validate. Place `YamlEditor` behind an explicit Advanced toggle. Preserve element picking and single-field/all-field testing; surface results in `MappingTable` rows rather than widget cell mutations.

- [ ] **Step 6: Run adapter tests and manual probe smoke test**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_adapter_studio_viewmodel.py tests/test_adapter_schema.py tests/test_element_picker.py tests/test_validation_summary.py tests/test_mapping_hints.py -v`

Expected: PASS.

Manual: probe a known adapter URL, generate mapping, edit one selector, verify stale state, run validation, then save. Expected: the task panel persists during navigation and save remains disabled until current YAML validates.

- [ ] **Step 7: Commit adapter studio**

```bash
git add crawler/app/workers crawler/app/ui_qml crawler/tests/ui_qml/test_adapter_studio_viewmodel.py
git commit -m "feat(crawler): migrate adapter builder to Site Studio"
```

## Task 6: Product Crawl Workflow

**Files:**
- Create: `crawler/app/workers/crawl.py`
- Create: `crawler/app/ui_qml/viewmodels/crawl.py`
- Create: `crawler/app/ui_qml/qml/screens/CrawlScreen.qml`
- Create: `crawler/app/ui_qml/qml/components/CategoryTree.qml`
- Create: `crawler/app/ui_qml/qml/components/CrawlResults.qml`
- Test: `crawler/tests/ui_qml/test_crawl_viewmodel.py`
- Modify: `crawler/app/ui_qml/application.py`
- Modify: `crawler/app/ui_qml/qml/components/AppShell.qml`

- [ ] **Step 1: Write validation, progress and cancellation tests**

```python
def test_start_requires_supplier_and_category(crawl_vm):
    assert crawl_vm.startCrawl() is False
    assert crawl_vm.fieldErrors == {
        "supplier": "도매처를 선택하세요.",
        "categories": "수집할 카테고리를 선택하세요.",
    }


def test_worker_progress_updates_shared_task(crawl_vm, fake_worker):
    crawl_vm.attachWorker(fake_worker)
    fake_worker.progress.emit("상품 3 수집 중")
    fake_worker.product_found.emit("셔츠", "P-3")
    assert crawl_vm.productCount == 1
    assert crawl_vm.appViewModel.activeTask.stage == "상품 3 수집 중"
```

- [ ] **Step 2: Run tests and verify missing ViewModel**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_crawl_viewmodel.py -v`

Expected: FAIL importing `CrawlViewModel`.

- [ ] **Step 3: Move the crawler worker without semantic changes**

Move `CrawlWorker` from `app/ui/tabs/crawl_tab.py` into `app/workers/crawl.py`. Preserve database writes, Playwright lifecycle, cancellation checks, result counts, and signal signatures. Add `cancelled = Signal(int, int)` and emit it instead of `finished` when `_cancelled` is true; keep the persisted `CrawlRun.status` value as `cancelled`.

- [ ] **Step 4: Implement crawl configuration and task mapping**

Expose suppliers, category tree nodes, selected category IDs, `maxPages`, `delaySeconds`, result rows, counts, field errors, and commands `discoverCategories()`, `toggleCategory(id, checked)`, `startCrawl()`, and `cancelCrawl()`. Map worker progress, product, completion, cancellation and error signals to the shared task state.

- [ ] **Step 5: Build the review-before-run screen**

Use three compact sections: supplier/category selection, crawl parameters/review, and results. During execution replace the primary action with Cancel while preserving configuration read-only. Display current target, elapsed time, counts and result rows. Do not duplicate the full log; link to the persistent task panel.

- [ ] **Step 6: Run tests and a cancellation smoke test**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_crawl_viewmodel.py tests/test_phase1_mapping_helpers.py tests/test_standard_schema.py -v`

Expected: PASS.

Manual: start a two-page crawl, navigate to Settings, return, then cancel. Expected: task remains visible, progress is retained, persisted run status is `cancelled`, and UI does not show an error banner.

- [ ] **Step 7: Commit product crawl workflow**

```bash
git add crawler/app/workers/crawl.py crawler/app/ui_qml crawler/tests/ui_qml/test_crawl_viewmodel.py
git commit -m "feat(crawler): migrate product crawl workflow to QML"
```

## Task 7: Stock Monitoring Dashboard

**Files:**
- Create: `crawler/app/ui_qml/viewmodels/monitor.py`
- Create: `crawler/app/ui_qml/qml/screens/MonitorScreen.qml`
- Create: `crawler/app/ui_qml/qml/components/MetricCard.qml`
- Create: `crawler/app/ui_qml/qml/components/DataTable.qml`
- Test: `crawler/tests/ui_qml/test_monitor_viewmodel.py`
- Modify: `crawler/app/ui_qml/application.py`
- Modify: `crawler/app/ui_qml/qml/components/AppShell.qml`

- [ ] **Step 1: Write filter, metric and acknowledgement tests**

```python
def test_unread_metric_and_type_filter(monitor_vm, seeded_changes):
    monitor_vm.refresh()
    assert monitor_vm.unreadCount == 2
    monitor_vm.setChangeType("sold_out")
    assert all(row["changeType"] == "sold_out" for row in monitor_vm.rows)


def test_acknowledge_selected_refreshes_unread_count(monitor_vm, seeded_changes):
    monitor_vm.selectChange(seeded_changes[0].id)
    monitor_vm.acknowledgeSelected()
    assert monitor_vm.unreadCount == 1
```

- [ ] **Step 2: Run tests and verify missing ViewModel**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_monitor_viewmodel.py -v`

Expected: FAIL importing `MonitorViewModel`.

- [ ] **Step 3: Implement query and mutation commands**

Expose metrics for unread, sold-out, restocked, price changes and failed schedules. Expose supplier and change-type filters, selected change ID, event roles, and commands `refresh()`, `setSupplierFilter(id)`, `setChangeType(type)`, `acknowledgeSelected()`, and `acknowledgeAll()`. Preserve timezone values and format dates in QML from ISO strings.

- [ ] **Step 4: Build metrics, filters, events and schedule status**

Place five compact metric cards above a virtualized event table. Use semantic status badges plus text labels. Put schedule state in the right detail drawer for the selected supplier. Unread state must use both font weight and a marker, never red text alone.

- [ ] **Step 5: Run ViewModel and stock checker tests**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_monitor_viewmodel.py tests/test_stock_checker.py -v`

Expected: PASS.

- [ ] **Step 6: Commit monitoring screen**

```bash
git add crawler/app/ui_qml crawler/tests/ui_qml/test_monitor_viewmodel.py
git commit -m "feat(crawler): add QML stock monitoring dashboard"
```

## Task 8: Validated Export Workflow

**Files:**
- Create: `crawler/app/ui_qml/viewmodels/export.py`
- Create: `crawler/app/ui_qml/qml/screens/ExportScreen.qml`
- Create: `crawler/app/ui_qml/qml/components/ValidationList.qml`
- Test: `crawler/tests/ui_qml/test_export_viewmodel.py`
- Modify: `crawler/app/ui_qml/application.py`
- Modify: `crawler/app/ui_qml/qml/components/AppShell.qml`

- [ ] **Step 1: Write validation and history tests**

```python
def test_export_is_blocked_when_scope_has_no_products(export_vm):
    export_vm.setSupplierId("empty-supplier")
    export_vm.validateScope()
    assert export_vm.canExport is False
    assert export_vm.issues[0]["severity"] == "error"


def test_recent_exports_are_newest_first(export_vm, tmp_path):
    import os

    older = tmp_path / "older.xlsx"
    newer = tmp_path / "newer.xlsx"
    older.touch()
    newer.touch()
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))
    export_vm.setExportDirectory(str(tmp_path))
    export_vm.refreshHistory()
    assert export_vm.history[0]["fileName"] == "newer.xlsx"
```

- [ ] **Step 2: Run tests and verify missing ViewModel**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_export_viewmodel.py -v`

Expected: FAIL importing `ExportViewModel`.

- [ ] **Step 3: Implement scope validation, file dialog and history**

Expose selected supplier, product/option counts, issues, output URL, `canExport`, and history rows. Use `QFileDialog.getSaveFileUrl()` behind a slot so QML does not own filesystem rules. Run export through a worker/task boundary if the dataset is nontrivial; map completion and failure to `AppVM.activeTask`.

```python
@Slot(result=bool)
def export(self) -> bool:
    self.validateScope()
    if not self._can_export or not self._output_path:
        return False
    self._app_vm.start_task("export", "엑셀 저장")
    self._run_export(self._supplier_id, self._output_path)
    return True
```

- [ ] **Step 4: Build the three-stage export screen**

Display Scope, Validation, and Destination in order. Errors block the primary button; warnings require acknowledgement but do not block. Recent history includes filename, time, row count and outcome. Selecting an issue opens the affected record in the detail drawer when an ID exists.

- [ ] **Step 5: Run export tests**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_export_viewmodel.py tests/test_excel_export.py -v`

Expected: PASS and generated workbooks retain the existing schema.

- [ ] **Step 6: Commit export workflow**

```bash
git add crawler/app/ui_qml crawler/tests/ui_qml/test_export_viewmodel.py
git commit -m "feat(crawler): add validated QML export workflow"
```

## Task 9: Settings and First-Run Experience

**Files:**
- Create: `crawler/app/ui_qml/viewmodels/settings.py`
- Create: `crawler/app/ui_qml/viewmodels/first_run.py`
- Create: `crawler/app/ui_qml/qml/screens/SettingsScreen.qml`
- Create: `crawler/app/ui_qml/qml/screens/FirstRunScreen.qml`
- Create: `crawler/app/ui_qml/qml/components/SettingsSection.qml`
- Test: `crawler/tests/ui_qml/test_settings_viewmodel.py`
- Test: `crawler/tests/ui_qml/test_first_run_viewmodel.py`
- Modify: `crawler/app/ui_qml/application.py`
- Modify: `crawler/app/ui_qml/qml/Main.qml`

- [ ] **Step 1: Write secret-presence, search and completion tests**

```python
def test_settings_exposes_secret_presence_not_value(settings_vm, monkeypatch):
    monkeypatch.setattr("app.ui_qml.viewmodels.settings.load_llm_api_key", lambda provider: "secret-value")
    settings_vm.load()
    assert settings_vm.geminiKeyConfigured is True
    assert "secret-value" not in repr(settings_vm)


def test_first_run_requires_provider_key_and_browser(first_run_vm):
    first_run_vm.setProvider("gemini")
    first_run_vm.setBrowserChannel("msedge")
    assert first_run_vm.complete() is False
    assert first_run_vm.fieldErrors["apiKey"] == "API 키를 입력하세요."
```

- [ ] **Step 2: Run tests and verify missing ViewModels**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_settings_viewmodel.py tests/ui_qml/test_first_run_viewmodel.py -v`

Expected: FAIL importing the ViewModels.

- [ ] **Step 3: Implement searchable settings and safe secret updates**

Expose config values, boolean key-presence properties, update-check state, and section metadata searchable by Korean and English labels. Secret inputs are write-only slots: QML sends a replacement value, but no property returns it. Saving an empty secret leaves the current keychain value unchanged; an explicit remove command deletes it.

- [ ] **Step 4: Implement first-run routing and persistence**

If `.first_run_done` is absent, `Main.qml` shows `FirstRunScreen` instead of `AppShell`. Completion saves provider/browser configuration, stores the key, creates the marker, and switches to the shell. Cancellation closes the app without creating the marker.

```qml
Loader {
    anchors.fill: parent
    sourceComponent: FirstRunVM.required ? firstRunComponent : shellComponent
}
```

- [ ] **Step 5: Build settings sections and verify key masking**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_settings_viewmodel.py tests/ui_qml/test_first_run_viewmodel.py tests/test_credentials_store.py -v`

Expected: PASS.

Manual: configure Gemini, switch to OpenAI, replace one key, remove the other, restart. Expected: fields never reveal stored keys and configured-state badges are correct.

- [ ] **Step 6: Commit settings and first run**

```bash
git add crawler/app/ui_qml crawler/tests/ui_qml/test_settings_viewmodel.py crawler/tests/ui_qml/test_first_run_viewmodel.py
git commit -m "feat(crawler): migrate settings and first-run flow to QML"
```

## Task 10: Native Window Effects, Reduced Motion, and Accessibility

**Files:**
- Create: `crawler/app/ui_qml/window_effects.py`
- Create: `crawler/tests/ui_qml/test_window_effects.py`
- Modify: `crawler/app/ui_qml/application.py`
- Modify: `crawler/app/ui_qml/qml/Theme.qml`
- Modify: `crawler/app/ui_qml/qml/Main.qml`
- Modify: shared components under `crawler/app/ui_qml/qml/components/`

- [ ] **Step 1: Write platform fallback tests**

```python
from app.ui_qml.window_effects import Backdrop, choose_backdrop


def test_windows_10_has_safe_color_fallback():
    assert choose_backdrop("win32", (10, 0, 19045), native_available=False) == Backdrop.COLOR


def test_windows_11_uses_mica_when_available():
    assert choose_backdrop("win32", (10, 0, 22631), native_available=True) == Backdrop.MICA


def test_macos_without_native_bridge_uses_color():
    assert choose_backdrop("darwin", (14, 0, 0), native_available=False) == Backdrop.COLOR
```

- [ ] **Step 2: Run tests and verify missing policy**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_window_effects.py -v`

Expected: FAIL importing `window_effects`.

- [ ] **Step 3: Implement an isolated enhancement policy**

```python
class Backdrop(str, Enum):
    MICA = "mica"
    ACRYLIC = "acrylic"
    VIBRANCY = "vibrancy"
    COLOR = "color"


def choose_backdrop(platform: str, version: tuple[int, ...], native_available: bool) -> Backdrop:
    if platform == "win32" and native_available and version >= (10, 0, 22000):
        return Backdrop.MICA
    if platform == "win32" and native_available:
        return Backdrop.ACRYLIC
    if platform == "darwin" and native_available:
        return Backdrop.VIBRANCY
    return Backdrop.COLOR
```

Keep ctypes/AppKit integration in this module. Catch capability and API failures, log one sanitized warning, and return `COLOR`. Never make application startup depend on a native backdrop.

- [ ] **Step 4: Apply reduced-motion and accessibility rules**

Add a `Theme.motionEnabled` property driven by the platform style hint when available and an environment override for tests. Every animation binds `duration: Theme.motionEnabled ? Theme.motionNormal : 0`. Add `Accessible.name`, role/state properties, logical `KeyNavigation`, visible focus rings, text labels for semantic states, and 44px minimum hit targets for primary actions.

- [ ] **Step 5: Run automated and manual accessibility checks**

Run: `cd crawler && .venv/bin/python -m pytest tests/ui_qml/test_window_effects.py tests/ui_qml/test_application.py -v`

Expected: PASS with offscreen rendering.

Manual on macOS: keyboard-traverse every screen, change theme, enable reduced motion, resize to 900x620 and test 200% scaling. Expected: no overlap, clipped primary action, invisible focus, or contrast-dependent text.

- [ ] **Step 6: Commit platform and accessibility behavior**

```bash
git add crawler/app/ui_qml crawler/tests/ui_qml/test_window_effects.py
git commit -m "feat(crawler): add adaptive window effects and accessibility"
```

## Task 11: Packaging Cutover and Legacy UI Removal

**Files:**
- Modify: `crawler/build_windows.spec`
- Modify: `crawler/README.md`
- Delete: `crawler/app/ui/main_window.py`
- Delete: `crawler/app/ui/first_run_wizard.py`
- Delete: `crawler/app/ui/tabs/`
- Delete: `crawler/app/ui/styles/global.qss`
- Test: `crawler/tests/ui_qml/test_application.py`

- [ ] **Step 1: Add a packaging-resource assertion**

```python
def test_all_qml_files_resolve_from_packaged_root(qt_app):
    engine = create_engine()
    warnings = engine.property("startupWarnings") or []
    assert warnings == []
    assert engine.rootObjects()[0].isVisible()
```

- [ ] **Step 2: Update PyInstaller inputs**

```python
# build_windows.spec Analysis changes
datas=[
    ("app/ui_qml/qml", "app/ui_qml/qml"),
    ("assets", "assets"),
],
hiddenimports=[
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "playwright",
    "keyring.backends",
    "keyring.backends.Windows",
    "apscheduler.schedulers.background",
    "apscheduler.triggers.interval",
    "pydantic",
    "yaml",
    "google.generativeai",
    "openai",
    "bs4",
    "pygments.lexers",
    "pygments.formatters",
],
```

Resolve QML paths through `sys._MEIPASS` when frozen and the source directory otherwise. Remove the QSS data entry.

- [ ] **Step 3: Prove no runtime imports the legacy UI**

Run: `cd crawler && rg -n "app\.ui\.|QtWidgets|global\.qss" main.py app --glob '*.py'`

Expected: no runtime results. Test-only use of `QtWidgets` may remain where it validates non-QML helpers.

- [ ] **Step 4: Remove the legacy UI and run all tests**

Delete `crawler/app/ui/` only after Step 3 is clean.

Run: `cd crawler && .venv/bin/python -m pytest tests/ -v`

Expected: all tests PASS.

- [ ] **Step 5: Build and inspect the macOS development bundle or directory build**

Run: `cd crawler && .venv/bin/pyinstaller --clean build_windows.spec`

Expected: build completes; `dist/AutoSelpCrawler/` includes QML and SVG assets; launching the executable produces no missing-module or missing-QML errors. The Windows-specific final build remains for Task 12.

- [ ] **Step 6: Update documentation and commit the cutover**

Update README screenshots/text references from tabs to sidebar workflows, document system theme behavior, and list Windows 10/11 as required verification targets.

```bash
git add -A crawler/app/ui crawler/app/ui_qml crawler/build_windows.spec crawler/README.md crawler/tests/ui_qml
git commit -m "refactor(crawler): complete QML UI cutover"
```

## Task 12: Cross-Platform Release Verification

**Files:**
- Create: `crawler/docs/qml-ui-release-checklist.md`
- Modify: `crawler/.github/workflows/build_windows.yml`
- Modify: `crawler/README.md`

- [ ] **Step 1: Add CI smoke tests before packaging**

```yaml
- name: Run crawler tests
  working-directory: crawler
  env:
    QT_QPA_PLATFORM: offscreen
  run: python -m pytest tests/ -v

- name: Build Windows package
  working-directory: crawler
  run: pyinstaller --clean build_windows.spec
```

- [ ] **Step 2: Run the full local verification suite**

Run: `cd crawler && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`

Expected: all tests PASS with zero QML load or binding errors.

- [ ] **Step 3: Verify macOS behavior using the release checklist**

Record PASS/FAIL for startup, shutdown, dark/light changes, transparency fallback, move/resize/minimize/maximize, Korean input, first run, keychain, all six workflows, active-task navigation, cancellation, minimum size, 100%/200% scaling, and installer-equivalent frozen launch. Fix every FAIL before proceeding.

- [ ] **Step 4: Build and verify Windows 10**

Trigger the Windows workflow or run `pyinstaller --clean build_windows.spec` on Windows 10. Install the generated package and execute the same checklist at 100%, 125%, and 150% scaling. Expected: native backdrop or color fallback, correct Korean text, working Edge selection, no console window, and successful crawl/export smoke flow.

- [ ] **Step 5: Build and verify Windows 11**

Install the same artifact on Windows 11 and execute the checklist at 100%, 150%, and 200% scaling. Expected: Mica when available, safe fallback otherwise, correct maximize/restore behavior, and successful crawl/export smoke flow.

- [ ] **Step 6: Record evidence and commit release verification**

The checklist records OS build, display scale, package version, result, and any fallback used. Do not mark the redesign complete while any required row is FAIL.

```bash
git add crawler/docs/qml-ui-release-checklist.md crawler/.github/workflows/build_windows.yml crawler/README.md
git commit -m "test(crawler): verify QML UI release targets"
```

## Final Completion Check

- [ ] Run `cd crawler && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` and confirm all tests pass.
- [ ] Confirm `rg -n "app\.ui\.|QtWidgets|global\.qss" crawler/main.py crawler/app --glob '*.py'` returns no production UI dependency.
- [ ] Confirm all six destinations are reachable by mouse and keyboard.
- [ ] Confirm active crawl and adapter tasks survive navigation and cancel distinctly from failure.
- [ ] Confirm system dark/light changes apply without restart.
- [ ] Confirm Windows 10, Windows 11, and macOS checklist rows are all PASS.
- [ ] Confirm credentials, cookies, API keys, and authorization headers never appear in UI logs or copied diagnostics.
- [ ] Run `git status --short` and verify only intentional changes remain.
