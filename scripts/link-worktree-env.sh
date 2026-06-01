#!/usr/bin/env bash
set -euo pipefail

SOURCE_ENV="${AUTO_SELP_ENV_SOURCE:-/Users/yoonjae/Desktop/auto-selp-ver2/.env}"
TARGET_ENV=".env"

if [ ! -f "$SOURCE_ENV" ]; then
  echo "Source env file not found: $SOURCE_ENV" >&2
  echo "Set AUTO_SELP_ENV_SOURCE to the correct .env path and retry." >&2
  exit 1
fi

if [ -e "$TARGET_ENV" ] || [ -L "$TARGET_ENV" ]; then
  echo ".env already exists; leaving it unchanged."
  exit 0
fi

ln -s "$SOURCE_ENV" "$TARGET_ENV"
echo "Linked .env -> $SOURCE_ENV"
