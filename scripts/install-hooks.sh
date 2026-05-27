#!/usr/bin/env bash
#
# Install repo-managed git hooks into .git/hooks/.
# Run once per fresh clone: ./scripts/install-hooks.sh
#
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_SRC="$REPO_ROOT/scripts/pre-commit"
HOOK_DST="$REPO_ROOT/.git/hooks/pre-commit"

cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"

echo "Installed pre-commit hook → $HOOK_DST"
