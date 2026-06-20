#!/usr/bin/env bash
# MindCare -- backend test runner (Linux)
# Зеркало test.ps1: compileall + pytest tests/ без запуска серверов.
# Использование: ./test.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT/mindcare_api"
VENV_PYTHON="$API_DIR/.venv/bin/python"

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo -e "${YELLOW}[TEST]  $*${NC}"; }
ok()   { echo -e "  ${GREEN}[OK]${NC}  $*"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $*"; exit 1; }

echo ""
echo -e "${YELLOW}==========================================${NC}"
echo -e "${YELLOW}       MindCare  --  Backend Tests        ${NC}"
echo -e "${YELLOW}==========================================${NC}"

# venv
if [ ! -x "$VENV_PYTHON" ]; then
  echo -e "${RED}  Python venv не найден ($VENV_PYTHON).${NC}"
  echo -e "${YELLOW}  Запустите ./start.sh или ./deploy.sh для создания venv.${NC}"
  exit 1
fi

# pytest
if ! "$VENV_PYTHON" -m pytest --version >/dev/null 2>&1; then
  echo -e "${RED}  pytest не установлен.${NC}"
  echo -e "${YELLOW}  Установите: $VENV_PYTHON -m pip install -r mindcare_api/requirements-dev.txt${NC}"
  exit 1
fi
ok "pytest: $("$VENV_PYTHON" -m pytest --version 2>&1 | head -1)"

# compileall
step "python -m compileall app ..."
( cd "$API_DIR" && "$VENV_PYTHON" -m compileall app -q ) || fail "compileall обнаружил синтаксические ошибки в app/."
ok "compileall: ошибок нет."

# pytest
step "pytest tests/ -v ..."
( cd "$API_DIR" && "$VENV_PYTHON" -m pytest tests/ -v ) || fail "Тесты упали. Исправьте ошибки перед запуском проекта."
ok "Все backend-тесты прошли."

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}          All checks passed  [OK]         ${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
