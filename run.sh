#!/usr/bin/env bash
set -euo pipefail

# Resolve script directory (project root)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$SCRIPT_DIR"

# Ensure uv is installed
if ! command -v uv >/dev/null 2>&1; then
  echo "Error: 'uv' is not installed. See https://docs.astral.sh/uv/ for installation instructions." >&2
  exit 1
fi

# Sync environment and run the app
uv sync
exec uv run python "${SCRIPT_DIR}/main.py"
