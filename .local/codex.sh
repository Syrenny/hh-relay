#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

if ! command -v sbx >/dev/null 2>&1; then
  echo "Error: sbx is not installed or not available in PATH" >&2
  exit 1
fi

exec sbx run codex