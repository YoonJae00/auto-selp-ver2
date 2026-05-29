---
title: "Docker Compose env_file truncates values containing $ (bcrypt secrets)"
date: 2026-05-30
category: docs/solutions/runtime-errors
module: processor
problem_type: runtime_error
component: tooling
symptoms:
  - "Environment variable inside container has value truncated at the first $ after the leading prefix (e.g., NAVER_COMMERCE_CLIENT_SECRET=$2a$04$ instead of $2a$04$DORTzMqXJ3ba679YI3tHMO)"
  - "Docker Compose warns: 'The \"<VARIABLE_NAME>\" variable is not set. Defaulting to a blank string.' for each $ sequence in the secret"
  - "Naver Commerce OAuth2 token fetch fails with cryptic bcrypt salt error or HTTP 401"
root_cause: config_error
resolution_type: config_change
severity: high
tags:
  - docker-compose
  - env-file
  - bcrypt
  - dollar-sign-escaping
  - naver-commerce-api
---

# Docker Compose env_file truncates values containing $ (bcrypt secrets)

## Problem

When a secret stored in `.env` contains literal `$` characters (e.g., bcrypt salts like `$2a$04$...`), Docker Compose treats each `$<WORD>` as a variable interpolation expression. The undefined portion is replaced with an empty string, causing the container to receive a truncated value.

## Symptoms

- `docker compose exec <service> env | grep <VAR>` shows the value cut off at the first `$` after the bcrypt prefix: `$2a$04$` instead of the full salt.
- Docker Compose prints one warning per `$` interpolation attempt during `up` / `exec`:
  ```
  level=warning msg="The \"DORTzMqXJ3ba679YI3tHMO\" variable is not set. Defaulting to a blank string."
  ```
- Any service logic that depends on the full secret (e.g., bcrypt signing for Naver Commerce OAuth2) fails at runtime — not at startup — because config reads succeed with the partial value.

## What Didn't Work

- Adding quotes around the value in `.env`: `NAVER_COMMERCE_CLIENT_SECRET='$2a$04$...'`  
  Docker Compose `env_file` does **not** strip quotes; the container receives the value with literal quote characters.

## Solution

Escape every `$` in the secret value with `$$` in `.env`. Docker Compose converts `$$` → `$` before injecting the variable into the container environment.

**Before (broken):**
```
NAVER_COMMERCE_CLIENT_SECRET=$2a$04$DORTzMqXJ3ba679YI3tHMO
```

**After (working):**
```
NAVER_COMMERCE_CLIENT_SECRET=$$2a$$04$$DORTzMqXJ3ba679YI3tHMO
```

After editing `.env`, restart the affected services:
```bash
docker compose up -d processor worker
```

Verify the full value is present:
```bash
docker compose exec processor env | grep NAVER_COMMERCE_CLIENT_SECRET
# Expected: NAVER_COMMERCE_CLIENT_SECRET=$2a$04$DORTzMqXJ3ba679YI3tHMO
```

## Why This Works

Docker Compose performs shell-style variable interpolation on all values in `.env` (both for `docker-compose.yml` substitution and for `env_file` injection). The `$$` sequence is the escape mechanism defined in the Docker Compose specification: it is treated as a single literal `$` rather than the start of a variable reference.

**Scope of interpolation:**
- **Top-level `.env`** (compose.yml substitution): `$VAR` → resolved from host environment; unset → empty string.
- **`env_file: .env`** (service environment injection): same interpolation rules apply, contrary to what some older documentation suggests.

## Prevention

1. **When storing any secret with special characters in `.env` for Docker Compose**, check for `$`, `{`, `}`. Escape all `$` as `$$`.
2. **Verify secrets are fully injected** after any `.env` change by running:
   ```bash
   docker compose exec <service> env | grep <SECRET_VAR>
   ```
3. **Add to onboarding docs**: Credentials from bcrypt-based APIs (e.g., Naver Commerce) contain `$` delimiters in the salt format — always escape them when recording in `.env`.

## Related Issues

- Naver Commerce OAuth2 authentication (`services/processor/clients/naver_commerce_client.py`) depends on this secret being intact.
- Python `pydantic-settings` reads the environment variable (not the raw `.env` file) inside the container, so it receives the correctly unescaped value when `$$` is used.
