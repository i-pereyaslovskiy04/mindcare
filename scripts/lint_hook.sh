#!/usr/bin/env bash
# PreToolUse-hook: ESLint-гейт перед git commit.
#
# Подключается в .claude/settings.json с matcher "Bash". Так как matcher
# фильтрует ТОЛЬКО имя инструмента (не аргументы), отбор `git commit` делается
# здесь — по tool_input.command из JSON, который хук получает на stdin.
#
# Коды выхода:
#   0 — пропустить (не git commit / npm недоступен / lint чистый)
#   2 — заблокировать вызов, stderr уходит в Claude
#
# npm резолвится через nvm: в неинтерактивном шелле ~/.bashrc не читается
# (ранний return для non-interactive), поэтому PATH достраивается явно.

set -u

payload=$(cat)

command=$(printf '%s' "$payload" | python3 -c \
  'import json,sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    pass' 2>/dev/null)

case "$command" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

NVM_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | tail -1)"
[ -n "$NVM_BIN" ] && PATH="$NVM_BIN:$PATH"

if ! command -v npm >/dev/null 2>&1; then
  echo "[MindCare] npm не найден — lint перед коммитом пропущен" >&2
  exit 0
fi

WEB_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}/mindcare_web"

if ! out=$(cd "$WEB_DIR" && npm run lint 2>&1); then
  echo "[MindCare] ESLint не прошёл — коммит остановлен:" >&2
  printf '%s\n' "$out" | tail -20 >&2
  exit 2
fi

exit 0
