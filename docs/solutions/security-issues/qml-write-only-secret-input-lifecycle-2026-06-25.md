---
title: Keep QML secret inputs write-only after save failures and success
date: 2026-06-25
category: security-issues
module: crawler QML settings and first run
problem_type: security_issue
component: authentication
symptoms:
  - API key text remained readable from a QML input after successful first-run completion
  - Credential save exceptions could echo the submitted API key into field errors
  - QML engine tests could touch the real user keyring through default view-model construction
root_cause: missing_validation
resolution_type: code_fix
severity: high
related_components:
  - "crawler QML test fixtures"
  - "settings view model"
tags:
  - "qml"
  - "secrets"
  - "keyring"
  - "first-run"
  - "settings"
---

# Keep QML secret inputs write-only after save failures and success

## Problem

Settings and first-run screens accepted API keys as write-only inputs, but successful saves and error paths still had ways to leave submitted secret text observable in process memory or UI state. The QML engine tests also instantiated production settings defaults, which could reach the developer's real keyring.

## Symptoms

- After clicking first-run completion, the app switched to the shell but the old `firstRunApiKeyInput` object could still be found with its previous `text`.
- A backend exception such as `RuntimeError("failed TOPSECRET")` from credential saving surfaced through `fieldErrors`.
- Generic `create_engine()` tests could evaluate `geminiKeyConfigured` or `openaiKeyConfigured` and call the real keyring.

## What Didn't Work

- Relying on `Loader` route switching to destroy or hide the first-run input. Hidden QML objects may still be present long enough for tests or diagnostics to read properties.
- Passing credential exceptions through the normal diagnostic sanitizer. Pattern-based redaction catches common `api_key=...` shapes, but arbitrary backend exception text can still contain the raw submitted secret.
- Only patching first-run state in QML engine fixtures. Settings view-model construction also has credential-presence properties that can call keyring.

## Solution

Clear secret text fields immediately after a successful write, before relying on navigation or component teardown:

```qml
if (root.viewModel.complete(provider, browser, apiKeyField.text)) {
    apiKeyField.text = ""
}
```

Use generic credential-operation errors for paths that have access to a submitted secret:

```python
try:
    key_saver(provider, submitted_key)
except Exception:
    set_field_errors({"apiKey": "API 키 저장에 실패했습니다."})
    return False
```

Patch both first-run and settings view models in QML engine tests so route rendering never calls the real user keyring:

```python
monkeypatch.setattr("app.ui_qml.application.SettingsViewModel", make_fake_settings)
monkeypatch.setattr("app.ui_qml.application.FirstRunViewModel", make_completed_first_run)
```

## Why This Works

Write-only is a lifecycle property, not just an API shape. A Python property may avoid returning stored keys, but a QML text field can still expose the submitted key until it is cleared. Generic credential errors avoid trying to predict every possible backend exception format, and test fixture isolation keeps deterministic tests from depending on or mutating a developer's local keyring state.

## Prevention

- Add UI tests that assert secret input fields are empty after successful save or completion.
- Add ViewModel tests where credential savers raise exceptions containing the submitted secret, and assert `fieldErrors` does not contain it.
- In engine-level QML tests, patch every ViewModel that can touch keychain/config state, not only the one under direct test.
- Treat hidden QML components as still observable until their secret-bearing fields are explicitly cleared.

## Related Issues

- [Safe QML supplier credential replacement lifecycle](qml-supplier-credential-replacement-lifecycle-2026-06-23.md)
