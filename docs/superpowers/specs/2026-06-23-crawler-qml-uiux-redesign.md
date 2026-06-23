# Crawler Qt Quick UI/UX Redesign

Date: 2026-06-23

## 1. Goal

Replace the crawler's PySide6 Widgets interface with a complete Qt Quick/QML interface while preserving the existing crawler, database, adapter, credential, monitoring, and export behavior.

The redesign must provide a compact, modern desktop workspace influenced by Codex: restrained translucent surfaces, clear hierarchy, persistent task visibility, system dark/light theme support, and focused motion. macOS is the primary development environment, but Windows 10 and Windows 11 are required release targets.

## 2. Scope

The redesign covers all six existing user-facing areas:

1. Supplier management
2. New-site registration and adapter building
3. Product crawling
4. Stock monitoring
5. Excel export
6. Settings

It also replaces the top-tab application shell with a collapsible sidebar, shared content header, persistent task panel, and contextual detail panel.

The following are out of scope:

- Changes to crawler extraction behavior or adapter semantics
- Database schema changes unrelated to UI state
- New marketplace integrations
- A web or Electron-based desktop shell
- Feature additions that are not required for functional parity or the approved workflow improvements

## 3. Technology Direction

- PySide6 remains the Python binding and packaging dependency.
- Qt Quick/QML replaces `QWidget`, `QMainWindow`, `QTabWidget`, and QSS as the primary UI layer.
- `QQmlApplicationEngine` loads the QML application.
- Python `QObject` ViewModels expose typed properties, signals, and slots to QML.
- Qt Quick Controls provide accessible interaction primitives; project-owned QML components provide visual styling.
- A project-owned token system controls color, spacing, typography, radius, borders, elevation, and motion.
- `Application.styleHints.colorScheme` drives the default system dark/light theme. A future explicit user override may be added without changing screen components.

The project will not depend on a third-party Fluent UI component library. This avoids external style and Qt-version coupling while keeping the design specific to the crawler's workflows.

## 4. Architecture

### 4.1 Layers

The desktop application is divided into four layers:

1. **Python Core**: existing crawler, database, adapter, credentials, monitoring, and export services.
2. **ViewModels**: the only UI-facing Python boundary. ViewModels translate service operations into commands and observable UI state.
3. **QML Screens**: application shell, screens, dialogs, panels, tables, forms, and feedback components.
4. **Design System**: shared tokens, controls, icons, effects, and motion behavior.

QML must not query SQLAlchemy sessions, invoke crawler engines, or handle Python exceptions directly. Screens communicate only with ViewModels and QML-owned presentation models.

### 4.2 ViewModel boundaries

The initial ViewModel set is:

- `AppViewModel`: navigation, active tasks, application-level notices, theme and window state
- `SuppliersViewModel`: supplier list, selection, create/edit/delete, connection and adapter status
- `AdapterStudioViewModel`: probe, analysis, mapping, validation, YAML advanced editing, save
- `CrawlViewModel`: supplier/category selection, crawl configuration, execution, progress and results
- `MonitorViewModel`: summary metrics, stock-change events, filters, acknowledgement and schedules
- `ExportViewModel`: export scope, validation, output selection and recent export history
- `SettingsViewModel`: general, browser, LLM provider, data and update settings

Each unit has one clear workflow responsibility. Shared long-running task state belongs to `AppViewModel`, not to an individual screen, so navigation does not detach or cancel an operation.

### 4.3 Long-running work

Existing worker and thread behavior is retained where practical. Worker events are converted to Qt signals and reflected through ViewModel properties. UI operations never block the Qt main thread.

All tasks use the common state model:

`idle -> validating -> running -> completed | failed | cancelled`

Progress may be determinate or indeterminate. A task records its label, stage, progress, sanitized log entries, start time, completion state, and actionable error when applicable.

## 5. Application Shell

The shell contains:

- A collapsible left sidebar for the six primary destinations
- A contextual content header with screen title, description, status and primary actions
- A central screen stack
- A collapsible bottom task panel showing current stage, progress, logs and errors
- An optional right detail panel for the selected supplier, product, event, or export issue

The bottom task panel persists while users navigate. It minimizes automatically when no active or failed task needs attention. The right panel is contextual and must not reduce the central content below its minimum usable width; at narrow window sizes it becomes an overlay drawer.

The compact layout targets dense operational work. Icon-only sidebar mode includes tooltips and accessible names. Navigation selection, task state, and panel visibility remain visually distinct in both themes.

## 6. Screen UX

### 6.1 Suppliers

Use a master-detail layout with supplier list and contextual detail. Each list item exposes connection state, adapter readiness, monitoring state, and last crawl time. Create and edit operations use a side sheet so users retain list context. Destructive actions require explicit confirmation and state the impact.

### 6.2 Site Studio

Combine new-site registration and adapter construction into a guided workspace:

1. Connect site
2. Analyze structure
3. Map fields
4. Validate and save

The normal workflow presents extracted fields and validation results rather than raw YAML. YAML remains available through an advanced editor with syntax highlighting, validation, and a clear indication of unsaved changes.

### 6.3 Product Crawl

Guide users through supplier selection, category selection, crawl configuration, and a final execution review. During execution, show current stage, product totals, success/failure counts, current target, elapsed time and progress. Results remain on the screen after completion and link to relevant errors or export actions.

### 6.4 Stock Monitoring

Present summary metrics above a filterable event list. Users can filter sold-out, restocked, price-change, and stock-change events. Supplier schedules, last checks, next checks and failure state are managed in the same screen without hiding event history.

### 6.5 Export

Organize export as scope selection, validation review, and file destination. Blocking errors and warnings are visible before writing a file. Validation items link back to the affected records when possible. Recent export history shows time, scope, row count, destination and outcome.

### 6.6 Settings

Group settings into General, Browser, AI Provider, Data, and Updates. Provide local search across setting names and descriptions. Secrets remain masked; the UI exposes only whether a key exists in the OS keychain. Updating a secret replaces the keychain entry without revealing its previous value.

## 7. Visual System

### 7.1 Color and surfaces

- Dark theme: charcoal background, translucent neutral panels, low-contrast borders, high-contrast content
- Light theme: warm off-white background, translucent white panels, neutral borders, dark content
- Accent: one restrained blue-violet or teal family used for selection, progress, focus and primary actions
- Semantic colors: success, warning and error are reserved for state communication

Blur is limited to the sidebar, task panel, popovers and selected overlay surfaces. Content cards rely primarily on subtle background and one-pixel border differences. Text contrast must not depend on the backdrop behind a translucent surface.

### 7.2 Platform behavior

- Windows 11 may use a native Mica/Acrylic-style backdrop where it can be integrated without breaking window behavior.
- Windows 10 uses a supported native effect when reliable, otherwise the project translucent-color fallback.
- macOS uses the platform-supported effect where reliable, otherwise the same fallback.
- Unsupported platforms and remote-rendering environments receive an opaque or translucent-color fallback with identical layout and contrast.

Native backdrop integration is an enhancement, not a dependency for readability or operation. Platform-specific code must be isolated behind one window-effects interface.

### 7.3 Typography, spacing and icons

- Use the system UI font for interface text and a platform-appropriate monospaced font for logs, URLs, identifiers and YAML.
- Use a four-pixel spacing grid.
- Default component radii range from 8 to 12 pixels.
- Use one consistent project-owned SVG icon family.
- Dense tables and forms remain keyboard navigable and retain visible focus indicators.

### 7.4 Motion

Motion durations stay between 120 and 220 milliseconds for sidebar collapse, panel transitions, selection, progress changes and notifications. Motion communicates state changes rather than decorating idle surfaces. When the operating system requests reduced motion, nonessential transitions are disabled and essential state changes become immediate.

## 8. Errors, Feedback and Safety

- Field validation appears adjacent to the affected input.
- Short-lived confirmation uses toast notifications.
- Persistent or blocking problems use inline banners or task-panel errors.
- Network, login, site-structure and filesystem errors provide a concise cause and a next action.
- User cancellation is distinct from failure.
- Python exceptions are converted to user-facing error objects before reaching QML.
- Detailed diagnostics may be copied from an expandable section, but stack traces are not shown by default.
- Logs and diagnostics sanitize credentials, API keys, cookies and authorization headers.
- Closing the app during active work requires confirmation and explains which task will stop.

## 9. Accessibility and Input

- All workflows support keyboard navigation and logical tab order.
- Controls expose accessible names, roles, descriptions and states.
- Focus is visible in dark and light themes.
- Color is never the only signal for status.
- Text and essential controls remain readable under all supported transparency fallbacks.
- Screen layouts support 100%, 125%, 150% and 200% display scaling.
- The minimum window size prevents controls from overlapping; below wide-layout thresholds, detail panels become drawers and multi-column forms collapse to one column.

## 10. Migration Strategy

The product outcome is a full replacement, but implementation proceeds in controlled stages:

1. Introduce the QML engine, resource loading, design tokens and shared shell.
2. Establish ViewModel contracts and shared task/error models.
3. Migrate all six screens in workflow order: Suppliers, Site Studio, Product Crawl, Monitoring, Export, Settings.
4. Keep the existing QWidget entry point available only as a development fallback until parity verification completes.
5. Remove the QWidget UI and global QSS after parity, packaging and platform validation pass.

Core service behavior must not be rewritten merely to accommodate QML. Where current UI classes contain business logic, that logic moves into a service or ViewModel with tests before the old widget is removed.

## 11. Testing and Verification

### 11.1 Automated tests

- Unit-test ViewModel commands, properties, state transitions and error conversion.
- Test presentation models independently from QML rendering.
- Add Qt Quick tests for reusable controls, screen state variants and keyboard navigation where practical.
- Run the existing crawler test suite unchanged to catch core regressions.
- Add startup tests that fail on QML import, resource, binding and required-root-object errors.

### 11.2 Manual platform matrix

Verify on macOS development builds and packaged Windows 10/11 builds:

- App startup and shutdown
- Dark/light system theme changes
- Native effect and fallback rendering
- Window movement, resize, minimize, maximize and restore
- Korean text input and display
- 100%, 125%, 150% and 200% display scaling
- Minimum-size and narrow-layout behavior
- Long-running task navigation, cancellation and close confirmation
- First-run wizard and keychain interactions
- PyInstaller resource inclusion and installer launch

## 12. Completion Criteria

The redesign is complete when:

1. All six existing screens have functional parity in QML.
2. The supplier-to-site-analysis-to-crawl-to-export flow works without entering the legacy UI.
3. Active tasks remain visible and controllable across navigation.
4. System dark/light changes update the interface without restarting.
5. Windows 10 and Windows 11 packaged builds launch and complete the primary workflow.
6. macOS development builds support the same primary workflow.
7. Platform effect fallbacks preserve contrast, layout and operation.
8. Keyboard access, visible focus, Korean text and supported DPI levels pass verification.
9. Existing crawler tests and new ViewModel/QML startup tests pass.
10. The legacy QWidget UI and QSS are removed only after the preceding criteria are satisfied.
