from __future__ import annotations

from contextlib import contextmanager

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPoint, Qt, QUrl, qInstallMessageHandler
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest

from app.config import AppConfig
from app.ui_qml.application import QML_DIRECTORY, create_engine
from app.ui_qml.viewmodels.settings import SettingsViewModel


@contextmanager
def capture_qt_messages():
    messages: list[str] = []

    def handler(_message_type, _context, message) -> None:
        messages.append(message)

    previous = qInstallMessageHandler(handler)
    try:
        yield messages
    finally:
        qInstallMessageHandler(previous)


def contrast_ratio(foreground: QColor, background: QColor) -> float:
    def luminance(color: QColor) -> float:
        channels = (color.redF(), color.greenF(), color.blueF())
        linear = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_qml_engine_loads_one_root_object(qt_app) -> None:
    with capture_qt_messages() as messages:
        engine = create_engine()

    root_objects = engine.rootObjects()
    assert len(root_objects) == 1
    assert root_objects[0].objectName() == "appWindow"
    qml_messages = [
        message
        for message in messages
        if "qml" in message.lower()
        or "binding loop" in message.lower()
        or "failed to load" in message.lower()
    ]
    assert not qml_messages


def test_qml_shell_exposes_persistent_layout_regions(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]

    assert root.findChild(QObject, "sidebar") is not None
    assert root.findChild(QObject, "contentStack") is not None
    assert root.findChild(QObject, "taskPanel") is not None


def test_app_view_model_is_retained_and_readable_from_qml(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    component.setData(
        b'import QtQml\nQtObject { property string route: AppVM.currentRoute }',
        QUrl(),
    )

    bound_object = component.create(engine.rootContext())

    assert b"appViewModel" in engine.dynamicPropertyNames()
    assert not component.errors()
    assert bound_object is not None
    assert bound_object.property("route") == "suppliers"


def test_monitor_view_model_is_retained_and_monitor_route_is_real_screen(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    monitor = root.findChild(QObject, "monitorScreen")

    assert b"monitorViewModel" in engine.dynamicPropertyNames()
    assert monitor is not None
    assert monitor.property("minimumContentWidth") == 620
    assert monitor.findChild(QObject, "monitorEventsTable") is not None
    assert monitor.findChild(QObject, "unreadMarkerLegend") is not None
    assert monitor.findChild(QObject, "ackSelectedButton").property("accessibleName")


def test_settings_view_models_are_retained_and_settings_route_is_real_screen(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    app_vm = engine.property("appViewModel")

    app_vm.navigate("settings")
    qt_app.processEvents()
    settings = root.findChild(QObject, "settingsScreen")

    assert b"settingsViewModel" in engine.dynamicPropertyNames()
    assert b"firstRunViewModel" in engine.dynamicPropertyNames()
    assert settings is not None
    assert settings.property("minimumContentWidth") == 620
    assert settings.findChild(QObject, "settingsSaveButton") is not None
    assert settings.findChild(QObject, "settingsBrowserSection") is not None


def test_settings_secret_inputs_clear_after_successful_save(qt_app, monkeypatch) -> None:
    saved_keys: dict[str, str] = {}

    def make_settings(parent=None):
        return SettingsViewModel(
            parent,
            config_loader=lambda: AppConfig(),
            config_saver=lambda _config: None,
            key_loader=lambda provider: saved_keys.get(provider),
            key_saver=lambda provider, key: saved_keys.__setitem__(provider, key),
            key_deleter=lambda provider: saved_keys.pop(provider, None),
        )

    monkeypatch.setattr("app.ui_qml.application.SettingsViewModel", make_settings)
    engine = create_engine()
    root = engine.rootObjects()[0]
    app_vm = engine.property("appViewModel")
    app_vm.navigate("settings")
    qt_app.processEvents()
    settings = root.findChild(QObject, "settingsScreen")
    gemini = settings.findChild(QObject, "geminiApiKeyInput")
    openai = settings.findChild(QObject, "openaiApiKeyInput")
    save = settings.findChild(QObject, "settingsSaveButton")
    gemini.setProperty("text", "gemini-secret")
    openai.setProperty("text", "openai-secret")

    assert QMetaObject.invokeMethod(save, "click") is True
    qt_app.processEvents()

    assert saved_keys == {"gemini": "gemini-secret", "openai": "openai-secret"}
    assert gemini.property("text") == ""
    assert openai.property("text") == ""


def test_qml_engine_tests_do_not_touch_real_keyring(qt_app, monkeypatch) -> None:
    def fail_keyring_access(*_args, **_kwargs):
        pytest.fail("QML engine tests must not touch the real keyring")

    monkeypatch.setattr("app.credentials.store.keyring.get_password", fail_keyring_access)
    engine = create_engine()
    root = engine.rootObjects()[0]
    app_vm = engine.property("appViewModel")

    app_vm.navigate("settings")
    qt_app.processEvents()

    assert engine.property("settingsViewModel").geminiKeyConfigured is False
    assert root.findChild(QObject, "settingsScreen") is not None


def test_monitor_schedule_detail_uses_shared_wide_and_overlay_drawers(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    app_vm = engine.property("appViewModel")
    monitor = root.findChild(QObject, "monitorScreen")
    wide = root.findChild(QObject, "detailDrawerWide")
    overlay = root.findChild(QObject, "detailDrawerOverlay")

    app_vm.navigate("monitor")
    assert QMetaObject.invokeMethod(monitor, "openScheduleDetail") is True
    qt_app.processEvents()

    assert wide.property("visible") is True
    assert wide.property("title") == "모니터 일정"
    for name in ("monitorLastCheckText", "monitorNextCheckText", "monitorFailureText"):
        field = wide.findChild(QObject, name)
        assert field is not None
        assert field.property("text")
    assert monitor.findChild(QObject, "monitorInlineSchedule") is None

    root.setWidth(900)
    qt_app.processEvents()

    assert wide.property("visible") is False
    assert overlay.property("visible") is True
    assert overlay.property("title") == "모니터 일정"
    for name in ("monitorLastCheckText", "monitorNextCheckText", "monitorFailureText"):
        field = overlay.findChild(QObject, name)
        assert field is not None
        assert field.property("text")


def test_export_issue_detail_reuses_wide_and_overlay_drawers(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    app_vm = engine.property("appViewModel")
    export_vm = engine.property("exportViewModel")
    export_vm._selected_issue_detail = {
        "productId": "p1", "code": "P-1", "name": "Product", "supplier": "Supplier",
        "status": "available", "price": 1200, "message": "원산지 누락", "severity": "warning",
    }
    export_vm.stateChanged.emit()
    app_vm.navigate("export")
    app_vm.set_detail_panel_open(True)
    qt_app.processEvents()

    wide = root.findChild(QObject, "detailDrawerWide")
    overlay = root.findChild(QObject, "detailDrawerOverlay")
    assert wide.property("visible") is True
    assert wide.property("title") == "내보내기 검증 상세"
    assert wide.findChild(QObject, "exportIssueCode").property("text") == "P-1"
    assert wide.findChild(QObject, "exportIssueMessage").property("text") == "원산지 누락"

    root.setWidth(900)
    qt_app.processEvents()
    assert wide.property("visible") is False
    assert overlay.property("visible") is True
    assert overlay.findChild(QObject, "exportIssueCode").property("text") == "P-1"


def test_export_warning_acknowledgement_tracks_view_model_resets(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    app_vm = engine.property("appViewModel")
    export_vm = engine.property("exportViewModel")
    app_vm.navigate("export")
    qt_app.processEvents()
    checkbox = root.findChild(QObject, "exportWarningAcknowledgement")
    button = root.findChild(QObject, "startExportButton")

    export_vm._warning_acknowledged = True
    export_vm.stateChanged.emit()
    qt_app.processEvents()
    assert checkbox.property("checked") is True

    export_vm._warning_acknowledged = False
    export_vm.stateChanged.emit()
    qt_app.processEvents()
    assert checkbox.property("checked") is False
    assert button.property("enabled") == export_vm.canExport

    assert QMetaObject.invokeMethod(checkbox, "click") is True
    qt_app.processEvents()
    assert export_vm.warningAcknowledged is True


def test_export_supplier_combo_starts_at_placeholder_and_tracks_vm_reset(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    export_vm = engine.property("exportViewModel")
    combo = root.findChild(QObject, "exportSupplierFilter")
    assert export_vm.selectedSupplierId == ""
    assert combo.property("currentIndex") == 0
    export_vm._suppliers.resetRows([{"id": "", "name": "도매처 선택"}, {"id": "s1", "name": "One"}])
    export_vm._supplier_ids = {"s1"}
    export_vm._supplier_names = {"s1": "One"}
    export_vm.setSupplierId("s1")
    qt_app.processEvents()
    assert combo.property("currentIndex") == 1

    export_vm.setSupplierId("")
    qt_app.processEvents()
    assert combo.property("currentIndex") == 0


def test_export_validation_issue_opens_drawer_from_keyboard(qt_app) -> None:
    from types import SimpleNamespace

    engine = create_engine()
    root = engine.rootObjects()[0]
    app_vm = engine.property("appViewModel")
    export_vm = engine.property("exportViewModel")
    issue = {"severity": "warning", "code": "missing_origin", "message": "원산지 누락", "productId": "p1", "productCode": "P-1"}
    export_vm._issues.resetRows([issue])
    product = SimpleNamespace(id="p1", supplier_product_code="P-1", raw_product_name="Product", supplier_name="Supplier", supplier_status="available", supply_price=1200)
    export_vm._session_factory = lambda: SimpleNamespace(get=lambda model, product_id: product, close=lambda: None)
    app_vm.navigate("export")
    qt_app.processEvents()
    validation_list = root.findChild(QObject, "exportValidationList")
    validation_list.setProperty("currentIndex", 0)
    assert QMetaObject.invokeMethod(validation_list, "forceActiveFocus") is True
    QTest.keyClick(root, Qt.Key.Key_Return)
    qt_app.processEvents()
    assert app_vm.detailPanelOpen is True
    assert root.findChild(QObject, "detailDrawerWide").findChild(QObject, "exportIssueCode").property("text") == "P-1"

def test_monitor_drawer_open_keeps_dashboard_horizontally_usable(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    app_vm = engine.property("appViewModel")
    monitor = root.findChild(QObject, "monitorScreen")
    scroll = monitor.findChild(QObject, "monitorScrollView")

    app_vm.navigate("monitor")
    app_vm.set_detail_panel_open(True)
    qt_app.processEvents()

    assert root.property("width") == 1180
    assert scroll.property("contentWidth") >= monitor.property("minimumContentWidth")
    assert scroll.property("contentWidth") >= scroll.property("availableWidth")
    for name in ("monitorRefreshButton", "ackSelectedButton", "monitorAckAllButton"):
        control = monitor.findChild(QObject, name)
        assert control is not None
        assert control.property("x") + control.property("width") <= control.parent().property("width")


def test_monitor_schedule_labels_estimated_next_check(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    component.setData(
        b'import QtQuick\nimport "components" as Components\n'
        b'Components.MonitorScheduleDetail { width: 300; height: 300; schedule: ({'
        b'nextCheckEstimated: true, nextCheckAt: "2026-06-24T13:00:00+00:00"}) }',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "MonitorScheduleProbe.qml")),
    )
    detail = component.create(engine.rootContext())
    next_check = detail.findChild(QObject, "monitorNextCheckText") if detail else None

    assert not component.errors()
    assert next_check is not None
    assert next_check.property("text").startswith("예상 다음 확인")


def test_theme_and_shared_control_can_be_instantiated(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    qml_url = QUrl.fromLocalFile(str(QML_DIRECTORY / "ThemeControlProbe.qml"))
    component.setData(
        b'''import QtQuick\nimport "." as Ui\nimport "components" as Components\n'''
        b'''Item { property color canvasToken: Ui.Theme.canvas\n'''
        b'''Components.AppButton { objectName: "probeButton"; text: "Probe" }\n'''
        b'''Components.DataTable { objectName: "probeTable"; accessibleName: "Probe table" } }''',
        qml_url,
    )

    with capture_qt_messages() as messages:
        probe = component.create(engine.rootContext())

    assert not component.errors()
    assert not messages
    assert probe is not None
    assert probe.findChild(QObject, "probeButton") is not None
    assert probe.findChild(QObject, "probeTable") is not None


def test_shell_animations_follow_disabled_motion_theme(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    component.setData(
        b'''import QtQuick\nimport "." as Ui\n'''
        b'''Item { Component.onCompleted: Ui.Theme.motionEnabled = false }''',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "MotionProbe.qml")),
    )

    probe = component.create(engine.rootContext())
    qt_app.processEvents()
    root = engine.rootObjects()[0]
    sidebar = root.findChild(QObject, "sidebar")
    task_panel = root.findChild(QObject, "taskPanel")

    assert not component.errors()
    assert probe is not None
    assert sidebar.property("animationDuration") == 0
    assert task_panel.property("animationDuration") == 0


def test_semantic_foregrounds_meet_wcag_contrast_in_both_themes(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    component.setData(
        b'''import QtQuick\nimport "." as Ui\nQtObject {\n'''
        b'''property color darkSurface: "#242424"\nproperty color lightSurface: "#FDFDFC"\n'''
        b'''property color successDark: Ui.Theme.successForegroundDark\n'''
        b'''property color warningDark: Ui.Theme.warningForegroundDark\n'''
        b'''property color dangerDark: Ui.Theme.dangerForegroundDark\n'''
        b'''property color successLight: Ui.Theme.successForegroundLight\n'''
        b'''property color warningLight: Ui.Theme.warningForegroundLight\n'''
        b'''property color dangerLight: Ui.Theme.dangerForegroundLight }''',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "ContrastProbe.qml")),
    )
    with capture_qt_messages() as messages:
        probe = component.create(engine.rootContext())

    assert not component.errors()
    assert not messages
    assert probe is not None
    for token in ("successDark", "warningDark", "dangerDark"):
        assert contrast_ratio(probe.property(token), probe.property("darkSurface")) >= 4.5
    for token in ("successLight", "warningLight", "dangerLight"):
        assert contrast_ratio(probe.property(token), probe.property("lightSurface")) >= 4.5


def test_detail_drawer_switches_between_wide_pane_and_overlay(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    view_model = engine.property("appViewModel")
    wide_drawer = root.findChild(QObject, "detailDrawerWide")
    overlay_drawer = root.findChild(QObject, "detailDrawerOverlay")
    scrim = root.findChild(QObject, "detailScrim")
    central_content = root.findChild(QObject, "centralContent")

    view_model.set_detail_panel_open(True)
    qt_app.processEvents()

    assert wide_drawer.property("visible") is True
    assert wide_drawer.property("modal") is False
    assert overlay_drawer.property("visible") is False
    assert scrim.property("visible") is False
    assert wide_drawer.property("width") == 320
    assert central_content.property("width") < 700

    root.setWidth(900)
    qt_app.processEvents()

    assert wide_drawer.property("visible") is False
    assert overlay_drawer.property("visible") is True
    assert overlay_drawer.property("modal") is True
    assert scrim.property("visible") is True
    assert overlay_drawer.property("x") >= 900 - overlay_drawer.property("width")
    assert central_content.property("width") > 600


def test_overlay_detail_drawer_takes_focus_and_escape_closes_it(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    root.setWidth(900)
    view_model = engine.property("appViewModel")
    overlay_drawer = root.findChild(QObject, "detailDrawerOverlay")
    content_stack = root.findChild(QObject, "contentStack")
    content_stack.setProperty("focus", True)
    qt_app.processEvents()

    view_model.set_detail_panel_open(True)
    qt_app.processEvents()

    assert overlay_drawer.property("activeFocus") is True

    QTest.keyClick(root, Qt.Key_Escape)
    qt_app.processEvents()

    assert view_model.property("detailPanelOpen") is False
    assert content_stack.property("activeFocus") is True


def test_overlay_detail_drawer_close_button_closes_it(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    root.setWidth(900)
    view_model = engine.property("appViewModel")
    overlay_drawer = root.findChild(QObject, "detailDrawerOverlay")
    close_button = overlay_drawer.findChild(QObject, "drawerCloseButton")

    view_model.set_detail_panel_open(True)
    qt_app.processEvents()

    assert close_button is not None
    assert QMetaObject.invokeMethod(close_button, "click") is True
    qt_app.processEvents()

    assert view_model.property("detailPanelOpen") is False


def test_modal_detail_drawer_traps_tab_and_backtab_focus(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    root.setWidth(900)
    view_model = engine.property("appViewModel")
    overlay_drawer = root.findChild(QObject, "detailDrawerOverlay")
    close_button = overlay_drawer.findChild(QObject, "drawerCloseButton")

    view_model.set_detail_panel_open(True)
    qt_app.processEvents()
    QTest.qWait(10)
    qt_app.processEvents()

    assert close_button.property("activeFocus") is True

    QTest.keyClick(root, Qt.Key_Tab)
    qt_app.processEvents()
    assert overlay_drawer.property("activeFocus") is True

    QTest.keyClick(root, Qt.Key_Backtab)
    qt_app.processEvents()
    assert overlay_drawer.property("activeFocus") is True


def test_data_table_fallback_rows_are_pointer_selectable(qt_app) -> None:
    engine = create_engine()
    component = QQmlComponent(engine)
    component.setData(
        b'''import QtQuick\nimport QtQuick.Controls.Basic\n'''
        b'''import "components" as Components\n'''
        b'''ApplicationWindow { id: probe; width: 300; height: 150; visible: true; property int activated: -1\n'''
        b'''Components.DataTable { anchors.fill: parent; model: ["first", "second"]; onRowActivated: index => probe.activated = index } }''',
        QUrl.fromLocalFile(str(QML_DIRECTORY / "DataTableProbe.qml")),
    )
    window = component.create(engine.rootContext())
    view = window.findChild(QObject, "dataTableView") if window else None

    assert not component.errors()
    assert window is not None
    assert view is not None
    QTest.qWaitForWindowExposed(window)
    window.requestActivate()
    QTest.qWaitForWindowActive(window)
    QTest.qWait(50)
    qt_app.processEvents()

    QTest.mouseClick(window, Qt.LeftButton, pos=QPoint(60, 54))
    qt_app.processEvents()

    assert view.property("currentIndex") == 1
    assert window.property("activated") == 1

    view.setProperty("focus", True)
    assert QMetaObject.invokeMethod(view, "forceActiveFocus") is True
    QTest.keyClick(window, Qt.Key_Return)
    qt_app.processEvents()
    assert window.property("activated") == 1

    view.setProperty("currentIndex", 0)
    QTest.keyClick(window, Qt.Key_Space)
    qt_app.processEvents()
    assert window.property("activated") == 0


def test_task_panel_log_view_tracks_newest_entry(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    view_model = engine.property("appViewModel")
    view_model.start_task("probe", "Probe")
    view_model.update_task("running", 0.5, "first")
    view_model.update_task("running", 0.6, "second")
    qt_app.processEvents()
    log_view = root.findChild(QObject, "taskLogView")

    assert log_view is not None
    assert log_view.property("cursorPosition") == len(log_view.property("text"))


def test_navigation_updates_content_stack_index(qt_app) -> None:
    engine = create_engine()
    root = engine.rootObjects()[0]
    content_stack = root.findChild(QObject, "contentStack")
    view_model = engine.property("appViewModel")

    assert content_stack is not None
    assert content_stack.property("currentIndex") == 0

    view_model.navigate("monitor")
    qt_app.processEvents()

    assert content_stack.property("currentIndex") == 3


def test_shutdown_coordinator_drains_after_both_view_models() -> None:
    from app.ui_qml.application import _shutdown_view_models

    order = []
    adapter = type("Adapter", (), {"shutdown": lambda self: order.append("adapter")})()
    crawl = type("Crawl", (), {"shutdown": lambda self: order.append("crawl")})()
    _shutdown_view_models(adapter, crawl, drain=lambda: order.append("drain"))
    assert order == ["adapter", "crawl", "drain"]
