---
title: Safe QML supplier credential replacement lifecycle
date: 2026-06-23
last_updated: 2026-06-23
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
- Name-derived keys collided for Korean names and normalized names such as `A B` and `a-b`.

## What Didn't Work

- Pre-filling a password field made edit validation easy, but violated the write-only secret boundary and retained sensitive data in UI state.
- Deriving `credential_key` from the supplier name is unsafe: normalization can produce empty or colliding slugs, and replacement can overwrite a live key in place.
- Clearing only the database key on login disable or replacement creates an orphaned keyring record.

## Solution

Treat an existing `credential_key` as an opaque capability:

1. `beginEdit()` exposes only `credentialsConfigured`; replacement username and password fields start blank.
2. If both replacement fields remain blank, preserve the existing key and allow ordinary supplier edits.
3. If either replacement field is entered, require both.
4. Assign a UUID to a new supplier before storing credentials, then generate a unique versioned key: `supplier:{supplier.id}:{uuid4().hex}`.
5. Generate a fresh versioned key for every replacement; never overwrite a credential key in place.
6. After the database commit succeeds, best-effort delete the previous key.
7. When login is disabled, commit `credential_key = None`, then best-effort delete the previous key.
8. If the database commit fails after creating a replacement, roll back and delete only the newly created key. Never delete the old referenced key.
9. Delete suppliers with bounded Core `DELETE` statements in dependency order, commit the database transaction, and only then delete the credential key.

```python
if supplier is None:
    supplier = Supplier(id=str(uuid4()), name=name, base_url=base_url)

if needs_login and password:
    credential_key = f"supplier:{supplier.id}:{uuid4().hex}"
    save_supplier_credentials(credential_key, username, password)
elif needs_login and is_editing:
    # Preserve the opaque key; migrating would require reading the secret.
    credential_key = supplier.credential_key
else:
    credential_key = None

try:
    session.commit()
except Exception:
    session.rollback()
    best_effort_delete_credentials(new_credential_key)
    return False

if old_key and (not needs_login or old_key != credential_key):
    best_effort_delete_credentials(old_key)
```

The QML password field and `draft.password` are both cleared on editor visibility or responsive-pane changes, while username and URL fields remain untouched. Form-level persistence failures are rendered in an accessible inline banner.

## Why This Works

The UI never needs the stored password to preserve credentials. The database key is sufficient to signal configuration and to keep the existing secret associated with the supplier. A supplier UUID isolates namespaces even when names normalize identically, while a random version suffix makes every replacement immutable. Saving the new key before changing the database prevents deleting the only usable secret when keyring storage fails. Committing database deletion before keyring cleanup ensures a failed database transaction never destroys the credential for a supplier that still exists.

A rename with no replacement intentionally keeps the previous opaque key. This is the safe exception: migrating to a slug derived from the new name would require reading the stored password, which the UI workflow must never do.

## Prevention

- Assert that `beginEdit()` never calls a credential loader.
- Test blank preservation, partial replacement rejection, replacement cleanup, login-disable cleanup, and credential-save failure safety independently.
- Test non-ASCII names and normalized-name collisions; replacing one supplier must never delete another supplier's key.
- Keep passwords out of list roles, selected detail maps, field errors, logs, and object representations.
- Give write-only QML fields explicit object IDs and test that visibility cleanup targets only the secret field.
- Model cross-store changes as an ordered lifecycle and include compensating cleanup for database failure after a new key is created.
- Use bounded SQL Core deletes for nested supplier data so ORM relationship cascades cannot load entire product collections into the UI thread.

## Related Issues

- No high-overlap solution document was found in `docs/solutions/`.
