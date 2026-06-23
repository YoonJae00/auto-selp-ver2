---
title: Safe QML supplier credential replacement lifecycle
date: 2026-06-23
category: security-issues
module: crawler supplier management
problem_type: security_issue
component: authentication
symptoms:
  - Editing a supplier loaded its stored password from the system keyring into UI-facing state
  - Renaming, replacing, or disabling supplier login could leave an obsolete keyring entry behind
  - Partial replacement credentials could overwrite or invalidate an existing login
root_cause: logic_error
resolution_type: code_fix
severity: high
tags: [crawler, qml, credentials, keyring, supplier, secret-lifecycle]
---

# Safe QML supplier credential replacement lifecycle

## Problem

The QML supplier editor originally treated stored credentials as editable form data. Editing called the credential loader, exposed the stored username, and temporarily loaded the password even though the UI only needed to know whether credentials existed. Credential updates also lacked a complete cleanup lifecycle when a supplier was renamed or login was disabled.

## Symptoms

- `beginEdit()` called `load_supplier_credentials()` and placed returned values into the draft.
- A blank edit depended on a password that had already been read from the keyring.
- Replacing credentials under a renamed supplier could leave the old credential key stored.
- Turning off `needs_login` cleared the database key without deleting the matching keyring entry.
- Supplying only a replacement username or password was not distinguished from preserving the existing opaque credential.

## What Didn't Work

- Pre-filling a password field made edit validation easy, but violated the write-only secret boundary and retained sensitive data in UI state.
- Regenerating `credential_key` on every rename is unsafe without reading the old password, because the secret cannot be migrated to the new slug.
- Clearing only the database key on login disable or replacement creates an orphaned keyring record.

## Solution

Treat an existing `credential_key` as an opaque capability:

1. `beginEdit()` exposes only `credentialsConfigured`; replacement username and password fields start blank.
2. If both replacement fields remain blank, preserve the existing key and allow ordinary supplier edits.
3. If either replacement field is entered, require both.
4. Save replacement credentials under the current `_slugify(name)` key before committing the database change.
5. After the database commit succeeds, delete the previous key when it differs from the replacement key.
6. When login is disabled, commit `credential_key = None`, then delete the previous key.
7. If saving the new credential fails, return a sanitized form error and never delete the existing key.

```python
if needs_login and password:
    save_supplier_credentials(slug, username, password)
    credential_key = slug
elif needs_login and is_editing:
    # Preserve the opaque key; migrating would require reading the secret.
    credential_key = supplier.credential_key
else:
    credential_key = None

session.commit()

if old_key and (not needs_login or old_key != credential_key):
    delete_supplier_credentials(old_key)
```

The QML password field is also cleared on editor visibility changes, while the URL field has a separate ID and remains untouched.

## Why This Works

The UI never needs the stored password to preserve credentials. The database key is sufficient to signal configuration and to keep the existing secret associated with the supplier. Requiring an explicit username/password pair makes replacement intentional. Saving the new key before changing the database prevents deleting the only usable secret when keyring storage fails, while deleting the old key after a successful database commit prevents normal replacement and disable flows from leaving stale credentials.

A rename with no replacement intentionally keeps the previous opaque key. This is the safe exception: migrating to a slug derived from the new name would require reading the stored password, which the UI workflow must never do.

## Prevention

- Assert that `beginEdit()` never calls a credential loader.
- Test blank preservation, partial replacement rejection, replacement cleanup, login-disable cleanup, and credential-save failure safety independently.
- Keep passwords out of list roles, selected detail maps, field errors, logs, and object representations.
- Give write-only QML fields explicit object IDs and test that visibility cleanup targets only the secret field.
- Model cross-store changes as an ordered lifecycle and include compensating cleanup for database failure after a new key is created.

## Related Issues

- No high-overlap solution document was found in `docs/solutions/`.
