---
title: Shared responsive detail drawers for QML dashboard screens
date: 2026-06-24
category: docs/solutions/design-patterns
module: crawler QML desktop UI
problem_type: design_pattern
component: tooling
severity: medium
applies_when:
  - "A QML screen needs the same detail content in wide and narrow window layouts"
  - "The application shell already owns responsive drawer, overlay, focus, and Escape behavior"
tags:
  - "qml"
  - "pyside6"
  - "responsive-layout"
  - "detail-drawer"
  - "accessibility"
  - "component-slot"
---

# Shared responsive detail drawers for QML dashboard screens

## Context

The crawler monitor dashboard initially rendered supplier schedule details in an inline panel visible only at wider screen sizes. That duplicated shell-level layout responsibilities and made the schedule disappear below the inline breakpoint, even though the application shell already provided a wide detail drawer and a narrow modal overlay with close, Escape, focus restoration, and focus trapping behavior.

## Guidance

Keep responsive detail-panel ownership in the application shell. Give the shared drawer a safe component slot and retain a default component when no route-specific detail is supplied:

```qml
property Component contentComponent: null

Loader {
    Layout.fillWidth: true
    Layout.fillHeight: true
    sourceComponent: root.contentComponent || defaultContent
}
```

Create route-specific detail content as an independent component with one explicit data dependency. The shell selects both the drawer title and component for the active route, and supplies the same component to the wide and overlay drawer instances:

```qml
DetailDrawer {
    title: currentRoute === "monitor" ? "모니터 일정" : "상세 정보"
    contentComponent: currentRoute === "monitor" ? monitorScheduleDetail : null
}
```

The screen should only decide when detail is relevant. Supplier-filter activation, pointer row selection, and keyboard row selection call the shell view model to open the panel. They should not implement their own width breakpoint or overlay.

Test the shared contract at both sides of the shell breakpoint. At a wide width, verify the wide drawer contains the route detail fields. At the minimum supported width, verify the overlay contains the same last-check, next-check, and failure fields. Preserve the shell's existing Escape, close-button, and focus-trap regression tests.

For dashboard metrics derived from different data domains, state filtering semantics explicitly. Monitor event metrics follow supplier and event-type filters, while failed schedule counts follow only the supplier filter because a schedule failure is not an event change type. A test should lock that distinction down.

## Why This Matters

A screen-local responsive panel can appear correct at the development width while silently dropping important content at smaller supported sizes. Centralizing the drawer boundary makes the route content portable across wide and modal presentations and reuses already-tested accessibility behavior. A `Component` plus `Loader` slot also avoids making the generic drawer depend directly on a specific route or view model.

## When to Apply

- When a dashboard has selected-item or schedule details that must survive layout breakpoints.
- When the shell already owns modal scrims, focus handling, or keyboard dismissal.
- When multiple routes need specialized drawer bodies without duplicating drawer chrome.
- When a metric combines event data with operational run or scheduler data.

## Examples

Avoid hiding essential details inside a screen-specific panel:

```qml
GlassPanel {
    visible: screen.width >= 900
    // Important detail content disappears below 900px.
}
```

Instead, expose the detail body as a component and let the shell's existing `wideDetailMode` choose the wide drawer or overlay. Keep stable `objectName` values on critical detail fields so tests can confirm that both loader instances expose equivalent information.

## Related

- [PySide QThread cancellation and application fixture](../test-failures/pyside-qthread-async-cancellation-and-application-fixture-2026-06-24.md)
