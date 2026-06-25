---
title: Require per-scale evidence in QML release checklists
date: 2026-06-25
category: documentation-gaps
module: crawler QML release verification
problem_type: documentation_gap
component: documentation
severity: medium
applies_when:
  - A release checklist is used as the gate for desktop UI platform support
  - Windows and macOS behavior must be verified across multiple display scales
  - Reviewers need to audit whether a platform row was marked PASS with enough evidence
tags: [qml, release-checklist, windows, display-scaling, evidence]
related_components:
  - crawler Windows packaging
  - crawler QML desktop UI
---

# Require per-scale evidence in QML release checklists

## Context

Task-level release evidence initially used platform summary rows plus plain checkbox lists. That shape captured the intended checks, but it allowed a Windows or macOS platform row to be marked PASS without proving that each required behavior passed at each required display scale.

The review finding was specifically about auditability: Windows 10 and Windows 11 both need the same release gate behaviors, and the checklist must not hide missing scale combinations such as Windows 10 at 200% or Windows 11 at 125%.

## Guidance

Use two layers in desktop release checklists:

1. A platform summary table for OS build, display scale, package version, result, fallback, and evidence.
2. A behavior matrix whose cells are `PASS`, `FAIL`, or `PENDING` for every required platform/scale combination.

Example:

```markdown
| Check | Windows 10 100% | Windows 10 125% | Windows 10 150% | Windows 10 200% | Evidence |
| --- | --- | --- | --- | --- | --- |
| Startup | PENDING | PENDING | PENDING | PENDING | launch log or screenshot |
| Korean input | PENDING | PENDING | PENDING | PENDING | typed field screenshot |
| Successful crawl/export smoke flow | PENDING | PENDING | PENDING | PENDING | crawl completes and exported workbook opens |
```

Add an explicit rule:

```markdown
Each matrix cell must be PASS, FAIL, or PENDING. Evidence must name the platform and display scale for each PASS or FAIL cell. A platform summary row can be PASS only when every required matrix cell for that platform and scale is PASS.
```

## Why This Matters

Display scaling defects are often platform-specific and do not show up in unit tests or a single smoke run. A summary-only checklist can falsely imply coverage when one scale or one behavior was never checked.

The matrix forces the evidence to match the release claim. It also gives reviewers a concrete surface to compare against the design spec, especially for required Windows 10/11 support.

## When to Apply

- Before marking a cross-platform desktop UI redesign complete.
- When a release gate includes display scaling, OS-specific native effects, keychain behavior, or packaging/frozen launch behavior.
- When CI verifies syntax and tests, but human/manual platform checks are still required.

## Examples

Regression tests can guard the checklist structure:

```python
assert "| Check | macOS 100% | macOS 200% | Windows 10 100% | Windows 10 125% | Windows 10 150% | Windows 10 200% | Windows 11 100% | Windows 11 125% | Windows 11 150% | Windows 11 200% | Evidence |" in text
assert "Each matrix cell must be PASS, FAIL, or PENDING." in text
assert "Evidence must name the platform and display scale for each PASS or FAIL cell." in text
```

## Related

- [Package the crawler QML runtime without legacy widgets](../tooling-decisions/qml-pyinstaller-cutover-without-legacy-widgets-2026-06-25.md)
