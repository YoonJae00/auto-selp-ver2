from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_workflow_runs_offscreen_tests_before_clean_pyinstaller_build() -> None:
    workflow = ROOT / ".github" / "workflows" / "build_windows.yml"
    text = workflow.read_text(encoding="utf-8")

    tests_index = text.index("Run crawler tests")
    build_index = text.index("Build Windows package")

    assert tests_index < build_index
    assert "QT_QPA_PLATFORM: offscreen" in text
    assert "python -m pytest tests/ -v" in text
    assert "pyinstaller --clean build_windows.spec" in text


def test_qml_release_checklist_records_required_platform_evidence() -> None:
    checklist = ROOT / "docs" / "qml-ui-release-checklist.md"
    text = checklist.read_text(encoding="utf-8")

    for required in (
        "macOS local verification",
        "Windows 10 verification",
        "Windows 11 verification",
        "OS build",
        "Display scale",
        "Package version",
        "Fallback used",
        "Startup",
        "Shutdown",
        "Dark/light theme",
        "Transparency or Mica fallback",
        "Korean input",
        "First run",
        "Keychain",
        "Suppliers workflow",
        "Adapter Studio workflow",
        "Crawl workflow",
        "Export workflow",
        "Monitor workflow",
        "Settings workflow",
        "Active-task navigation",
        "Cancellation",
        "Minimum size",
        "Frozen launch",
    ):
        assert required in text

    assert "| Platform | OS build | Display scale | Package version | Result | Fallback used | Evidence |" in text
    assert "| Check | macOS 100% | macOS 200% | Windows 10 100% | Windows 10 125% | Windows 10 150% | Windows 10 200% | Windows 11 100% | Windows 11 125% | Windows 11 150% | Windows 11 200% | Evidence |" in text
    assert "Each matrix cell must be PASS, FAIL, or PENDING." in text
    assert "Evidence must name the platform and display scale for each PASS or FAIL cell." in text
    assert "A platform summary row can be PASS only when every required matrix cell for that platform and scale is PASS." in text
    assert "Do not mark the QML redesign complete while any required row is FAIL." in text


def test_readme_links_release_checklist_and_windows_targets() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "docs/qml-ui-release-checklist.md" in readme
    assert "Windows 10" in readme
    assert "Windows 11" in readme
    assert "100%" in readme
    assert "200%" in readme
