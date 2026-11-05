#!/usr/bin/env bash
set -euo pipefail

if [[ "${VERCEL_ENV:-}" == "production" ]]; then
  uv run --frozen alembic upgrade head
fi
