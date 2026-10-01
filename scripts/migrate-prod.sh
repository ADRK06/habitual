#!/usr/bin/env bash
# Thin wrapper - see migrate_prod.py for the actual (shell-free) env loading
# and safety checks.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/migrate_prod.py" "$@"
