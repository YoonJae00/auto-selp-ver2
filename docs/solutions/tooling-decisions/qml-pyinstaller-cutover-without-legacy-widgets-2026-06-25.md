---
title: Package the crawler QML runtime without legacy widgets
date: 2026-06-25
category: tooling-decisions
module: crawler QML packaging
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - Migrating a PySide desktop app from QWidget screens to Qt Quick QML
  - Packaging QML screens with PyInstaller for Windows 10 and Windows 11
  - Removing legacy UI files while preserving test and export behavior
tags: [qml, pyside6, pyinstaller, windows-packaging, legacy-cutover]
related_components:
  - crawler QML export
  - crawler desktop UI tests
---

# Package the crawler QML runtime without legacy widgets

## Context

The crawler desktop UI moved from legacy QWidget tabs and QSS styling to a Qt Quick/QML shell. The packaging cutover needed to remove the old runtime files, keep Windows 10/11 packaging viable, and avoid regressing the export save flow when `QFileDialog` was removed.

Two details made this easy to miss:

- PyInstaller does not automatically prove the intended QML resource layout from ordinary unit tests.
- Replacing `QFileDialog.getSaveFileUrl()` with QML `FileDialog` removes the old implicit suggested filename unless the ViewModel exposes one.

## Guidance

Treat a QML cutover as a packaging contract, not only a source-code deletion.

The runtime should resolve QML files differently in source and frozen builds:

```python
def resolve_qml_directory() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "app" / "ui_qml" / "qml"
    return Path(__file__).parent / "qml"
```

The Windows spec should package the QML tree and assets, and should list QML modules that are used directly by the screens:

```python
datas=[
    ("app/ui_qml/qml", "app/ui_qml/qml"),
    ("assets", "assets"),
]
hiddenimports=[
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickDialogs2",
]
```

When moving the export save dialog into QML, keep filename and path policy in Python. The ViewModel can expose a dialog URL while still hiding the raw output path as mutable UI state:

```python
dialogSelectedFile = Property(
    QUrl,
    lambda self: QUrl.fromLocalFile(str(self._output_path or self._exports_dir / "export.xlsx")),
    notify=stateChanged,
)
```

Then QML uses that URL only to seed the native dialog:

```qml
onClicked: {
    exportFileDialog.selectedFile = root.viewModel.dialogSelectedFile
    exportFileDialog.open()
}
```

The accepted path still goes back through `setOutputPath()`, where the ViewModel converts `file:` URLs and enforces `.xlsx`.

## Why This Matters

QML-only runtime work can appear complete when source tests pass, while the packaged app still fails to locate QML files or misses a Qt Quick dialog module. Keeping the PyInstaller spec under test catches those omissions before a Windows build attempt.

Removing `QtWidgets` from runtime imports also narrows the application model to `QGuiApplication`, which is the intended shape for the QML shell. If a legacy dialog or QSS file remains referenced, the migration is not actually complete and the Windows packaging surface stays larger than necessary.

## When to Apply

- During PySide QWidget-to-QML migrations.
- Before deleting legacy `app/ui` screens or `global.qss`.
- When introducing QML modules such as `QtQuick.Dialogs` that may need packaging coverage.
- When README build instructions depend on dev tooling such as PyInstaller.

## Examples

Useful regression checks for this cutover:

```python
def test_windows_spec_packages_qml_and_assets_without_legacy_qss_or_widgets():
    text = Path("build_windows.spec").read_text(encoding="utf-8")

    assert '("app/ui_qml/qml", "app/ui_qml/qml")' in text
    assert '("assets", "assets")' in text
    assert "app/ui/styles/global.qss" not in text
    assert "PySide6.QtWidgets" not in text
    assert "PySide6.QtQuickDialogs2" in text
```

Also keep a source scan in the verification checklist:

```bash
rg -n "app\.ui\.|QtWidgets|global\.qss" main.py app build_windows.spec --glob '*.py' --glob '*.spec'
```

For a complete cutover, this command should return no matches.

## Related

- [Make QML export startup atomic and reuse the shell detail drawer](../integration-issues/qml-export-startup-atomicity-and-issue-detail-2026-06-24.md)
- [Shared responsive detail drawers for QML dashboard screens](../design-patterns/qml-shared-responsive-detail-drawer-2026-06-24.md)
- [PySide QML and QWidget tests require QApplication and real async cancellation](../test-failures/pyside-qthread-async-cancellation-and-application-fixture-2026-06-24.md)
