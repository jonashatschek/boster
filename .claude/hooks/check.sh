#!/usr/bin/env bash
# Stop hook: when Claude finishes a turn with uncommitted code changes, run the
# checks for the parts that changed. On failure, exit 2 so Claude sees the
# output and keeps working. Skips when nothing changed since the last pass.
set -u

input=$(cat)
# Already continuing because of this hook: don't loop forever.
if printf '%s' "$input" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
cd "$root" || exit 0

changed=$(git status --porcelain --untracked-files=all -- backend frontend 2>/dev/null)
[ -z "$changed" ] && exit 0

# Skip if the working tree is identical to the last state that passed.
stamp_file="$root/.claude/hooks/.last-pass"
stamp=$( { git diff HEAD -- backend frontend; git ls-files --others --exclude-standard -- backend frontend | while read -r f; do printf '%s\n' "$f"; cat "$f" 2>/dev/null; done; } | git hash-object --stdin)
[ -f "$stamp_file" ] && [ "$(cat "$stamp_file")" = "$stamp" ] && exit 0

out=""
fail=0

if printf '%s\n' "$changed" | grep -qE '^.. backend/.*\.(py|toml)$'; then
  py="$root/backend/.venv/Scripts/python.exe"
  [ -x "$py" ] || py="$root/backend/.venv/bin/python"
  [ -x "$py" ] || py=python
  if ! res=$(cd backend && "$py" -m pytest -q -x 2>&1); then
    fail=1; out+=$'Backend tests failed:\n'"$(printf '%s\n' "$res" | tail -40)"$'\n'
  fi
fi

if printf '%s\n' "$changed" | grep -qE '^.. frontend/(src/|.*\.(json|ts)$)'; then
  if ! res=$(cd frontend && npm run lint --silent 2>&1 && npx tsc -b 2>&1); then
    fail=1; out+=$'Frontend lint/typecheck failed:\n'"$(printf '%s\n' "$res" | tail -40)"$'\n'
  fi
fi

if [ "$fail" -ne 0 ]; then
  printf '%s' "$out" >&2
  exit 2
fi

printf '%s' "$stamp" > "$stamp_file"
exit 0
